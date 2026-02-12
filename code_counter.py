#!/usr/bin/env python3
"""
Code Counter: count total lines of code in a project and per-author contribution.

Features:
- Respects .gitignore (basic pattern support).
- Counts total lines by file extension.
- Counts per-author lines using `git blame --line-porcelain`.
- Works as a library and as a CLI tool.

"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator
from collections import defaultdict
import subprocess
import re
import argparse


__version__ = "0.1.1"
__all__ = ["CodeCounter", "GitIgnoreParser", "analyze_project"]


class GitIgnoreParser:
    def __init__(self, gitignore_path: Path | None = None) -> None:
        self.patterns: list[str] = []
        if gitignore_path and gitignore_path.exists():
            self._parse_gitignore(gitignore_path)

    def _parse_gitignore(self, path: Path) -> None:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                self.patterns.append(line.replace("\\", "/"))

    def should_ignore(self, path: Path, project_root: Path) -> bool:
        if ".git" in path.parts:
            return True

        rel = path.relative_to(project_root)
        rel_str = rel.as_posix()

        for pattern in self.patterns:
            pat = pattern

            if pat.endswith("/"):
                dir_prefix = pat.rstrip("/")
                if rel_str == dir_prefix or rel_str.startswith(dir_prefix + "/"):
                    return True
                continue

            if "*" in pat:
                regex_pattern = re.escape(pat).replace(r"\*", ".*")
                if re.search(regex_pattern, rel_str):
                    return True
                continue

            if pat == rel_str or rel_str.endswith(pat) or (pat in rel_str):
                return True

        return False


class CodeCounter:
    def __init__(self, project_path: str | Path) -> None:
        self.project_path = Path(project_path).resolve()
        self.gitignore_parser = GitIgnoreParser(self.project_path / ".gitignore")

        self.code_extensions = {
            ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp",
            ".h", ".hpp", ".cs", ".go", ".rs", ".rb", ".php", ".swift",
            ".kt", ".scala", ".sql", ".html", ".css", ".scss", ".vue",
            ".yaml", ".yml", ".json", ".xml", ".sh", ".bash", ".r",
            ".m", ".mm", ".dart", ".lua", ".pl",
        }

    def _is_code_file(self, path: Path) -> bool:
        return path.suffix.lower() in self.code_extensions

    def _count_lines_in_file(self, path: Path) -> int:
        try:
            with path.open("rb") as f:
                return sum(1 for _ in f)
        except (PermissionError, OSError):
            return 0

    def get_code_files(self) -> Iterator[Path]:
        for path in self.project_path.rglob("*"):
            if not path.is_file():
                continue

            if self.gitignore_parser.should_ignore(path, self.project_path):
                continue

            if self._is_code_file(path):
                yield path

    def count_total_lines(self) -> dict[str, int]:
        stats: dict[str, int] = defaultdict(int)
        total = 0

        for file_path in self.get_code_files():
            lines = self._count_lines_in_file(file_path)
            ext = (file_path.suffix or "no_ext").lower()
            stats[ext] += lines
            total += lines

        stats["TOTAL"] = total
        return dict(stats)

    def count_by_author(self) -> dict[str, int]:
        if not (self.project_path / ".git").exists():
            raise ValueError("Not a git repository (no .git directory found).")

        author_stats: dict[str, int] = defaultdict(int)

        for file_path in self.get_code_files():
            relative_path = file_path.relative_to(self.project_path).as_posix()

            try:
                result = subprocess.run(
                    ["git", "blame", "--line-porcelain", "--encoding=UTF-8", "--", relative_path],
                    cwd=self.project_path,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=60,
                )
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError):
                continue

            if result.returncode != 0 or not result.stdout:
                continue

            for line in result.stdout.splitlines():
                if line.startswith("author "):
                    author = line[7:].strip() or "Unknown"
                    author_stats[author] += 1

        return dict(sorted(author_stats.items(), key=lambda x: x[1], reverse=True))

    def get_stats_by_file(self) -> dict[str, int]:
        file_stats: dict[str, int] = {}
        for file_path in self.get_code_files():
            lines = self._count_lines_in_file(file_path)
            rel = file_path.relative_to(self.project_path).as_posix()
            file_stats[rel] = lines
        return dict(sorted(file_stats.items(), key=lambda x: x[1], reverse=True))


def analyze_project(project_path: str | Path, show_files: bool = False) -> None:
    counter = CodeCounter(project_path)

    print()
    print(f"Project: {counter.project_path}")
    print()

    print("=" * 50)
    print("Total lines by file type:")
    print("=" * 50)

    total_stats = counter.count_total_lines()
    total_lines = total_stats.pop("TOTAL", 0)

    for ext, lines in sorted(total_stats.items(), key=lambda x: x[1], reverse=True):
        print(f"  {ext:15s}: {lines:>8,} lines")

    print("-" * 50)
    print(f"  {'TOTAL':15s}: {total_lines:>8,} lines")
    print("=" * 50)

    print()
    print("=" * 50)
    print("Author contribution (git blame):")
    print("=" * 50)

    try:
        author_stats = counter.count_by_author()
        if not author_stats:
            print("  No author data (git blame returned nothing).")
        else:
            max_name_len = max(len(name) for name in author_stats.keys())
            for author, lines in author_stats.items():
                pct = (lines / total_lines * 100.0) if total_lines > 0 else 0.0
                print(f"  {author:{max_name_len}s}: {lines:>8,} lines ({pct:>5.1f}%)")
    except ValueError as e:
        print(f"  Author analysis skipped: {e}")
    except FileNotFoundError:
        print("  Author analysis failed: git not found in PATH.")
    except Exception as e:
        print(f"  Author analysis failed: {e}")

    print("=" * 50)

    if show_files:
        print()
        print("=" * 50)
        print("Top 10 largest files:")
        print("=" * 50)

        file_stats = counter.get_stats_by_file()
        for i, (file_path, lines) in enumerate(list(file_stats.items())[:10], 1):
            print(f"  {i:2d}. {file_path:60s} {lines:>8,} lines")

        print("=" * 50)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Count lines of code in a project (respects .gitignore; optional git blame stats)."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project path (default: current directory).",
    )
    parser.add_argument(
        "-f", "--files",
        action="store_true",
        help="Show top 10 largest files.",
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"code-counter {__version__}",
    )

    args = parser.parse_args()
    analyze_project(args.path, show_files=args.files)


if __name__ == "__main__":
    main()
