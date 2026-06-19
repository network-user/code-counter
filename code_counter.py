#!/usr/bin/env python3
"""
Code Counter: count physical lines in a project and per-author contribution.

Features:
- Respects .gitignore (wildcards, **, anchors, dir-only and negation patterns).
- Counts physical lines by file extension.
- Counts per-author lines using `git blame --incremental` (parallelized).
- Works as a library and as a CLI tool.
"""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator
import argparse
import json
import os
import re
import subprocess


__version__ = "0.2.0"
__all__ = ["CodeCounter", "GitIgnoreParser", "Analysis", "analyze_project"]


_HEXDIGITS = set("0123456789abcdef")


def _is_sha(token: str) -> bool:
    return len(token) == 40 and all(c in _HEXDIGITS for c in token)


class _Pattern:
    """A single compiled .gitignore pattern."""

    __slots__ = ("regex", "negation", "dir_only")

    def __init__(self, regex: re.Pattern[str], negation: bool, dir_only: bool) -> None:
        self.regex = regex
        self.negation = negation
        self.dir_only = dir_only


class GitIgnoreParser:
    """Parse a .gitignore file with the most common git semantics.

    Supported: wildcards (`*`, `?`, `[...]`), `**`, leading/middle `/` anchoring,
    trailing `/` (directory-only), basename matching at any level, and `!` negation.
    """

    def __init__(self, gitignore_path: Path | None = None) -> None:
        self.patterns: list[_Pattern] = []
        if gitignore_path and gitignore_path.exists():
            self._parse_gitignore(gitignore_path)

    def _parse_gitignore(self, path: Path) -> None:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for raw_line in f:
                self._add_pattern(raw_line)

    def _add_pattern(self, raw_line: str) -> None:
        line = raw_line.rstrip("\n").rstrip("\r")
        # Trailing whitespace is insignificant unless escaped (rare); keep it simple.
        line = line.rstrip()
        if not line:
            return

        # A leading backslash escapes a special first char (#, !).
        if line[0] in "\\":
            line = line[1:]
        elif line[0] == "#":
            return

        negation = False
        if line.startswith("!"):
            negation = True
            line = line[1:]
        if not line:
            return

        line = line.replace("\\", "/")

        dir_only = line.endswith("/")
        core = line.rstrip("/")

        anchored = core.startswith("/")
        if anchored:
            core = core[1:]
        elif "/" in core:
            anchored = True
        if not core:
            return

        body = self._translate(core)
        prefix = "^" if anchored else "^(?:.*/)?"
        try:
            regex = re.compile(prefix + body + "$")
        except re.error:
            return
        self.patterns.append(_Pattern(regex, negation, dir_only))

    @staticmethod
    def _translate(pat: str) -> str:
        """Translate a gitignore glob into a regex body (path separator = '/')."""
        out: list[str] = []
        i, n = 0, len(pat)
        while i < n:
            c = pat[i]
            if c == "*":
                if pat[i : i + 2] == "**":
                    if pat[i : i + 3] == "**/":
                        out.append("(?:.*/)?")
                        i += 3
                        continue
                    if i + 2 == n:
                        out.append(".*")
                        i += 2
                        continue
                    out.append("[^/]*")
                    i += 2
                    continue
                out.append("[^/]*")
                i += 1
            elif c == "?":
                out.append("[^/]")
                i += 1
            elif c == "[":
                j = i + 1
                if j < n and pat[j] in "!^":
                    j += 1
                if j < n and pat[j] == "]":
                    j += 1
                while j < n and pat[j] != "]":
                    j += 1
                if j >= n:
                    out.append(re.escape("["))
                    i += 1
                else:
                    inner = pat[i + 1 : j]
                    if inner.startswith("!"):
                        inner = "^" + inner[1:]
                    out.append("[" + inner + "]")
                    i = j + 1
            elif c == "/":
                out.append("/")
                i += 1
            else:
                out.append(re.escape(c))
                i += 1
        return "".join(out)

    def should_ignore(self, path: Path, project_root: Path, is_dir: bool = False) -> bool:
        if ".git" in path.parts:
            return True
        if not self.patterns:
            return False

        rel = path.relative_to(project_root).as_posix()
        if not rel or rel == ".":
            return False

        parts = rel.split("/")
        # Evaluate every ancestor directory, then the node itself. A pattern's
        # last match wins; if any ancestor ends up ignored, the path is ignored.
        for k in range(1, len(parts) + 1):
            sub = "/".join(parts[:k])
            sub_is_dir = True if k < len(parts) else is_dir
            decision: bool | None = None
            for p in self.patterns:
                if p.dir_only and not sub_is_dir:
                    continue
                if p.regex.match(sub):
                    decision = not p.negation
            if decision is True:
                return True
            if decision is False and k == len(parts):
                return False
        return False


@dataclass
class Analysis:
    project_path: Path
    lines_by_ext: dict[str, int]
    total_lines: int
    lines_by_author: dict[str, int]
    author_total: int
    files: dict[str, int] = field(default_factory=dict)
    author_error: str | None = None

    def to_dict(self) -> dict:
        return {
            "project_path": str(self.project_path),
            "total_lines": self.total_lines,
            "lines_by_ext": self.lines_by_ext,
            "lines_by_author": self.lines_by_author,
            "author_total": self.author_total,
            "author_error": self.author_error,
            "files": self.files,
        }


# Default set of extensions treated as code. The counter is language-agnostic
# (it counts physical lines, not syntax), so this list only decides which files
# are *picked up*. Use all_text=True / --all-text to count any text file instead.
DEFAULT_CODE_EXTENSIONS = frozenset({
    # Python
    ".py", ".pyw", ".pyx", ".pxd", ".pyi",
    # C / C++
    ".c", ".cc", ".cxx", ".cpp", ".c++", ".h", ".hh", ".hpp", ".hxx", ".h++", ".inl",
    # C# / .NET
    ".cs", ".vb", ".fs", ".fsx", ".fsi",
    # JVM
    ".java", ".kt", ".kts", ".scala", ".groovy", ".gradle",
    ".clj", ".cljs", ".cljc",
    # JavaScript / TypeScript
    ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx",
    # Web / markup / templates
    ".html", ".htm", ".css", ".scss", ".sass", ".less",
    ".vue", ".svelte", ".astro", ".xaml", ".qml", ".jsp",
    ".cshtml", ".razor", ".erb", ".phtml", ".ejs", ".hbs",
    # Go / Rust
    ".go", ".rs",
    # Ruby / PHP / Perl
    ".rb", ".rake", ".php", ".pl", ".pm", ".pod",
    # Swift / Objective-C
    ".swift", ".m", ".mm",
    # Shell / scripts
    ".sh", ".bash", ".zsh", ".fish", ".ps1", ".psm1", ".bat", ".cmd",
    # Functional / other languages
    ".hs", ".lhs", ".ml", ".mli", ".ex", ".exs", ".erl", ".hrl",
    ".elm", ".lisp", ".scm", ".rkt", ".dart", ".lua", ".r",
    ".jl", ".nim", ".zig", ".v", ".sv", ".svh", ".vhd", ".vhdl",
    ".asm", ".s", ".pas", ".pp", ".d", ".cr", ".vala", ".hx",
    ".tcl", ".awk", ".coffee", ".styl",
    # Data / config / IDL
    ".sql", ".yaml", ".yml", ".json", ".json5", ".xml", ".toml",
    ".ini", ".cfg", ".conf", ".properties", ".proto",
    ".graphql", ".gql",
    # Infra
    ".tf", ".tfvars", ".hcl", ".nix", ".bzl", ".cmake", ".dockerfile",
})

# Files recognized as code by name (no useful extension).
DEFAULT_CODE_FILENAMES = frozenset({
    "Makefile", "GNUmakefile", "Dockerfile", "Containerfile",
    "CMakeLists.txt", "Rakefile", "Gemfile", "Vagrantfile", "Justfile",
})


class CodeCounter:
    def __init__(
        self,
        project_path: str | Path,
        extensions: Iterable[str] | None = None,
        *,
        extra_extensions: Iterable[str] | None = None,
        all_text: bool = False,
    ) -> None:
        self.project_path = Path(project_path).resolve()
        self.gitignore_parser = GitIgnoreParser(self.project_path / ".gitignore")
        base = DEFAULT_CODE_EXTENSIONS if extensions is None else frozenset(extensions)
        exts = {e.lower() if e.startswith(".") else "." + e.lower() for e in base}
        if extra_extensions:
            exts |= {e.lower() if e.startswith(".") else "." + e.lower() for e in extra_extensions}
        self.code_extensions = frozenset(exts)
        self.code_filenames = DEFAULT_CODE_FILENAMES
        self.all_text = all_text
        self._code_files: list[Path] | None = None
        self._line_counts: dict[Path, int] | None = None

    @staticmethod
    def _is_text_file(path: Path) -> bool:
        """Heuristic: a file is text if its first block has no NUL byte."""
        try:
            with path.open("rb") as f:
                chunk = f.read(8192)
        except (PermissionError, OSError):
            return False
        return b"\x00" not in chunk

    def _is_code_file(self, path: Path) -> bool:
        if self.all_text:
            return self._is_text_file(path)
        if path.suffix.lower() in self.code_extensions:
            return True
        return path.name in self.code_filenames

    @staticmethod
    def _count_lines_in_file(path: Path) -> int:
        try:
            count = 0
            last = b""
            with path.open("rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    count += chunk.count(b"\n")
                    last = chunk[-1:]
            if last and last != b"\n":  # final line without trailing newline
                count += 1
            return count
        except (PermissionError, OSError):
            return 0

    def get_code_files(self) -> list[Path]:
        if self._code_files is None:
            self._code_files = list(self._scan())
        return self._code_files

    def _scan(self) -> Iterator[Path]:
        root = self.project_path
        for dirpath, dirnames, filenames in os.walk(root):
            dpath = Path(dirpath)
            # Prune ignored directories so we never descend into node_modules,
            # .venv, dist, etc. Editing dirnames in place controls os.walk.
            dirnames[:] = [
                d
                for d in dirnames
                if d != ".git"
                and not self.gitignore_parser.should_ignore(dpath / d, root, is_dir=True)
            ]
            for fn in filenames:
                fpath = dpath / fn
                if self.gitignore_parser.should_ignore(fpath, root):
                    continue
                if self._is_code_file(fpath):
                    yield fpath

    def _counts(self) -> dict[Path, int]:
        if self._line_counts is None:
            self._line_counts = {
                f: self._count_lines_in_file(f) for f in self.get_code_files()
            }
        return self._line_counts

    def count_total_lines(self) -> dict[str, int]:
        stats: dict[str, int] = defaultdict(int)
        total = 0
        for file_path, lines in self._counts().items():
            ext = (file_path.suffix or "no_ext").lower()
            stats[ext] += lines
            total += lines
        result = dict(stats)
        result["TOTAL"] = total
        return result

    def get_stats_by_file(self) -> dict[str, int]:
        items = {
            f.relative_to(self.project_path).as_posix(): n
            for f, n in self._counts().items()
        }
        return dict(sorted(items.items(), key=lambda x: x[1], reverse=True))

    def _blame_file(self, file_path: Path) -> dict[str, int]:
        relative_path = file_path.relative_to(self.project_path).as_posix()
        try:
            result = subprocess.run(
                ["git", "blame", "--incremental", "--encoding=UTF-8", "--", relative_path],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError):
            return {}
        if result.returncode != 0 or not result.stdout:
            return {}
        return self._parse_incremental(result.stdout)

    @staticmethod
    def _parse_incremental(output: str) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        sha_author: dict[str, str] = {}
        cur_sha: str | None = None
        cur_num = 0
        for line in output.splitlines():
            parts = line.split()
            if len(parts) >= 4 and _is_sha(parts[0]):
                cur_sha = parts[0]
                cur_num = int(parts[3])
                # `author` metadata only appears the first time a commit is seen.
                if cur_sha in sha_author:
                    counts[sha_author[cur_sha]] += cur_num
                    cur_sha = None
            elif cur_sha is not None and line.startswith("author "):
                author = line[7:].strip() or "Unknown"
                sha_author[cur_sha] = author
                counts[author] += cur_num
                cur_sha = None
        return dict(counts)

    def count_by_author(self, jobs: int | None = None) -> dict[str, int]:
        if not (self.project_path / ".git").exists():
            raise ValueError("Not a git repository (no .git directory found).")

        files = self.get_code_files()
        if not files:
            return {}

        workers = jobs or min(16, (os.cpu_count() or 4) + 4)
        author_stats: dict[str, int] = defaultdict(int)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for counts in pool.map(self._blame_file, files):
                for author, n in counts.items():
                    author_stats[author] += n

        return dict(sorted(author_stats.items(), key=lambda x: x[1], reverse=True))

    def analyze(self, *, with_author: bool = True, jobs: int | None = None) -> Analysis:
        totals = self.count_total_lines()
        total_lines = totals.pop("TOTAL", 0)

        author_stats: dict[str, int] = {}
        author_error: str | None = None
        if not with_author:
            author_error = "disabled (--no-blame)."
        if with_author:
            try:
                author_stats = self.count_by_author(jobs=jobs)
            except ValueError as e:
                author_error = str(e)
            except FileNotFoundError:
                author_error = "git not found in PATH."
            except Exception as e:  # pragma: no cover - defensive
                author_error = str(e)

        return Analysis(
            project_path=self.project_path,
            lines_by_ext=dict(sorted(totals.items(), key=lambda x: x[1], reverse=True)),
            total_lines=total_lines,
            lines_by_author=author_stats,
            author_total=sum(author_stats.values()),
            files=self.get_stats_by_file(),
            author_error=author_error,
        )


def _print_report(analysis: Analysis, show_files: bool, top: int) -> None:
    bar = "=" * 50
    print()
    print(f"Project: {analysis.project_path}")
    print()

    print(bar)
    print("Physical lines by file type:")
    print(bar)
    for ext, lines in analysis.lines_by_ext.items():
        print(f"  {ext:15s}: {lines:>8,} lines")
    print("-" * 50)
    print(f"  {'TOTAL':15s}: {analysis.total_lines:>8,} lines")
    print(bar)

    print()
    print(bar)
    print("Author contribution (git blame):")
    print(bar)
    if analysis.author_error:
        print(f"  Author analysis skipped: {analysis.author_error}")
    elif not analysis.lines_by_author:
        print("  No author data (git blame returned nothing).")
    else:
        max_name_len = max(len(name) for name in analysis.lines_by_author)
        base = analysis.author_total or 1
        for author, lines in analysis.lines_by_author.items():
            pct = lines / base * 100.0
            print(f"  {author:{max_name_len}s}: {lines:>8,} lines ({pct:>5.1f}%)")
    print(bar)

    if show_files:
        print()
        print(bar)
        print(f"Top {top} largest files:")
        print(bar)
        for i, (file_path, lines) in enumerate(list(analysis.files.items())[:top], 1):
            print(f"  {i:2d}. {file_path:60s} {lines:>8,} lines")
        print(bar)


def analyze_project(
    project_path: str | Path,
    show_files: bool = False,
    *,
    top: int = 10,
    with_author: bool = True,
    jobs: int | None = None,
    as_json: bool = False,
    all_text: bool = False,
    extra_extensions: Iterable[str] | None = None,
) -> Analysis:
    counter = CodeCounter(
        project_path, extra_extensions=extra_extensions, all_text=all_text
    )
    analysis = counter.analyze(with_author=with_author, jobs=jobs)
    if as_json:
        print(json.dumps(analysis.to_dict(), ensure_ascii=False, indent=2))
    else:
        _print_report(analysis, show_files=show_files, top=top)
    return analysis


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Count lines of code in a project (respects .gitignore; optional git blame stats)."
    )
    parser.add_argument(
        "path", nargs="?", default=".", help="Project path (default: current directory)."
    )
    parser.add_argument(
        "-f", "--files", action="store_true", help="Show the largest files."
    )
    parser.add_argument(
        "-n", "--top", type=int, default=10, help="How many largest files to show (default: 10)."
    )
    parser.add_argument(
        "--no-blame", action="store_true", help="Skip per-author git blame analysis."
    )
    parser.add_argument(
        "--all-text",
        action="store_true",
        help="Count every text file, not just known code extensions.",
    )
    parser.add_argument(
        "--ext",
        nargs="+",
        metavar="EXT",
        default=None,
        help="Extra extensions to treat as code, e.g. --ext .foo .bar",
    )
    parser.add_argument(
        "-j", "--jobs", type=int, default=None, help="Parallel git blame workers."
    )
    parser.add_argument(
        "--json", action="store_true", help="Output machine-readable JSON."
    )
    parser.add_argument(
        "-v", "--version", action="version", version=f"code-counter {__version__}"
    )

    args = parser.parse_args()
    analyze_project(
        args.path,
        show_files=args.files,
        top=args.top,
        with_author=not args.no_blame,
        jobs=args.jobs,
        as_json=args.json,
        all_text=args.all_text,
        extra_extensions=args.ext,
    )


if __name__ == "__main__":
    main()
