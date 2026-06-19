from pathlib import Path

from code_counter import GitIgnoreParser


def make_parser(tmp_path: Path, lines: list[str]) -> GitIgnoreParser:
    gi = tmp_path / ".gitignore"
    gi.write_text("\n".join(lines), encoding="utf-8")
    return GitIgnoreParser(gi)


def ignored(parser: GitIgnoreParser, root: Path, rel: str, is_dir: bool = False) -> bool:
    return parser.should_ignore(root / rel, root, is_dir=is_dir)


def test_wildcard_extension(tmp_path):
    p = make_parser(tmp_path, ["*.pyc"])
    assert ignored(p, tmp_path, "a.pyc")
    assert ignored(p, tmp_path, "src/b.pyc")
    assert not ignored(p, tmp_path, "a.py")


def test_no_false_substring_match(tmp_path):
    # The old parser used `pattern in path`, which wrongly ignored mylibrary.
    p = make_parser(tmp_path, ["lib"])
    assert ignored(p, tmp_path, "lib", is_dir=True)
    assert ignored(p, tmp_path, "lib/x.py")
    assert not ignored(p, tmp_path, "mylibrary/main.py")
    assert not ignored(p, tmp_path, "public/main.py")


def test_directory_only_pattern(tmp_path):
    p = make_parser(tmp_path, ["build/"])
    assert ignored(p, tmp_path, "build", is_dir=True)
    assert ignored(p, tmp_path, "build/out.js")
    # A regular file literally named "build" must not be ignored.
    assert not ignored(p, tmp_path, "build", is_dir=False)


def test_anchored_pattern(tmp_path):
    p = make_parser(tmp_path, ["/dist"])
    assert ignored(p, tmp_path, "dist/x.js")
    assert not ignored(p, tmp_path, "src/dist/x.js")


def test_negation(tmp_path):
    p = make_parser(tmp_path, ["*.log", "!keep.log"])
    assert ignored(p, tmp_path, "a.log")
    assert not ignored(p, tmp_path, "keep.log")


def test_globstar(tmp_path):
    p = make_parser(tmp_path, ["**/temp"])
    assert ignored(p, tmp_path, "temp", is_dir=True)
    assert ignored(p, tmp_path, "a/b/temp", is_dir=True)


def test_git_dir_always_ignored(tmp_path):
    p = make_parser(tmp_path, [])
    assert ignored(p, tmp_path, ".git/config")


def test_comments_and_blank_lines(tmp_path):
    p = make_parser(tmp_path, ["# comment", "", "  ", "*.tmp"])
    assert ignored(p, tmp_path, "x.tmp")
    assert not ignored(p, tmp_path, "comment")
