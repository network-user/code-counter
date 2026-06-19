import shutil
import subprocess

import pytest

from code_counter import CodeCounter


def test_count_lines_with_and_without_trailing_newline(tmp_path):
    counter = CodeCounter(tmp_path)
    (tmp_path / "a.py").write_text("x\ny\nz", encoding="utf-8")  # no trailing newline
    (tmp_path / "b.py").write_text("x\ny\n", encoding="utf-8")
    (tmp_path / "c.py").write_text("", encoding="utf-8")
    assert counter._count_lines_in_file(tmp_path / "a.py") == 3
    assert counter._count_lines_in_file(tmp_path / "b.py") == 2
    assert counter._count_lines_in_file(tmp_path / "c.py") == 0


def test_get_code_files_respects_extensions_and_gitignore(tmp_path):
    (tmp_path / ".gitignore").write_text("ignored/\n*.skip\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("a\nb\n", encoding="utf-8")
    (tmp_path / "app.js").write_text("a\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("a\n", encoding="utf-8")  # not a code ext
    (tmp_path / "x.skip").write_text("a\n", encoding="utf-8")     # gitignored
    (tmp_path / "ignored").mkdir()
    (tmp_path / "ignored" / "deep.py").write_text("a\n", encoding="utf-8")

    counter = CodeCounter(tmp_path)
    names = {f.name for f in counter.get_code_files()}
    assert names == {"main.py", "app.js"}


def test_count_total_lines(tmp_path):
    (tmp_path / "main.py").write_text("a\nb\nc\n", encoding="utf-8")
    (tmp_path / "app.js").write_text("a\nb\n", encoding="utf-8")
    counter = CodeCounter(tmp_path)
    totals = counter.count_total_lines()
    assert totals[".py"] == 3
    assert totals[".js"] == 2
    assert totals["TOTAL"] == 5


def test_all_text_mode_counts_any_file(tmp_path):
    (tmp_path / "main.py").write_text("a\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("a\nb\n", encoding="utf-8")
    counter = CodeCounter(tmp_path, all_text=True)
    names = {f.name for f in counter.get_code_files()}
    assert {"main.py", "notes.txt"} <= names


def test_all_text_skips_binary(tmp_path):
    (tmp_path / "data.bin").write_bytes(b"\x00\x01\x02binary\x00")
    counter = CodeCounter(tmp_path, all_text=True)
    names = {f.name for f in counter.get_code_files()}
    assert "data.bin" not in names


def test_extra_extensions(tmp_path):
    (tmp_path / "doc.md").write_text("a\nb\n", encoding="utf-8")
    counter = CodeCounter(tmp_path, extra_extensions=["md"])
    names = {f.name for f in counter.get_code_files()}
    assert "doc.md" in names


def test_recognized_by_filename(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    counter = CodeCounter(tmp_path)
    names = {f.name for f in counter.get_code_files()}
    assert "Dockerfile" in names


def test_parse_incremental():
    sha = "a" * 40
    output = "\n".join([
        f"{sha} 1 1 3",
        "author Alice",
        "author-mail <alice@example.com>",
        "summary first",
        "filename foo.py",
        f"{sha} 4 4 2",  # same commit, author not repeated
    ])
    counts = CodeCounter._parse_incremental(output)
    assert counts == {"Alice": 5}


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_count_by_author_real_repo(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True,
                       capture_output=True, text=True)

    git("init")
    git("config", "user.email", "tester@example.com")
    git("config", "user.name", "Tester")
    git("config", "core.autocrlf", "false")
    (tmp_path / "foo.py").write_text("a\nb\nc\n", encoding="utf-8")
    git("add", "foo.py")
    git("commit", "-m", "init")

    counter = CodeCounter(tmp_path)
    authors = counter.count_by_author()
    assert authors == {"Tester": 3}
