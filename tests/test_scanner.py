"""Unit tests for the scanner subsystem."""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from repomedic.cli.main import cli
from repomedic.scanner import DEFAULT_IGNORE_DIRS, FileScanner, ScanError, ScanResult
from repomedic.scanner.models import FileEntry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def simple_repo(tmp_path: Path) -> Path:
    """A minimal fake repository with known content."""
    (tmp_path / "README.md").write_text("# Hello")
    (tmp_path / "main.py").write_text("print('hello')")
    (tmp_path / "utils.py").write_text("pass")
    (tmp_path / "data.json").write_text("{}")

    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("pass")
    (src / "config.py").write_text("pass")

    sub = src / "helpers"
    sub.mkdir()
    (sub / "strings.py").write_text("pass")

    return tmp_path


@pytest.fixture()
def repo_with_ignored(tmp_path: Path) -> Path:
    """A repo that contains directories that should be ignored."""
    (tmp_path / "app.py").write_text("pass")

    for ignored in (".git", "__pycache__", "node_modules", "venv", ".venv"):
        d = tmp_path / ignored
        d.mkdir()
        (d / "artifact").write_text("should not appear")

    # A real sub-package should still be scanned
    pkg = tmp_path / "mypackage"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")

    return tmp_path


# ---------------------------------------------------------------------------
# FileEntry model tests
# ---------------------------------------------------------------------------


class TestFileEntry:
    def test_from_path_basic(self, tmp_path: Path) -> None:
        f = tmp_path / "hello.py"
        f.write_text("content")
        entry = FileEntry.from_path(f, tmp_path)

        assert entry.absolute_path == f
        assert entry.relative_path == Path("hello.py")
        assert entry.filename == "hello.py"
        assert entry.extension == ".py"
        assert entry.size_bytes == len("content")

    def test_extension_is_lowercased(self, tmp_path: Path) -> None:
        f = tmp_path / "Report.CSV"
        f.write_text("a,b,c")
        entry = FileEntry.from_path(f, tmp_path)
        assert entry.extension == ".csv"

    def test_no_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "Makefile"
        f.write_text("all:")
        entry = FileEntry.from_path(f, tmp_path)
        assert entry.extension == ""

    def test_is_frozen(self, tmp_path: Path) -> None:
        f = tmp_path / "x.txt"
        f.write_text("x")
        entry = FileEntry.from_path(f, tmp_path)
        with pytest.raises((AttributeError, TypeError)):
            entry.filename = "y.txt"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ScanResult model tests
# ---------------------------------------------------------------------------


class TestScanResult:
    def test_file_count(self, simple_repo: Path) -> None:
        result = FileScanner().scan(simple_repo)
        assert result.file_count == 7  # 4 root + 2 src + 1 helpers

    def test_extension_counts(self, simple_repo: Path) -> None:
        result = FileScanner().scan(simple_repo)
        ext = result.extension_counts
        assert ext[".py"] == 5
        assert ext[".md"] == 1
        assert ext[".json"] == 1

    def test_extension_counts_sorted_by_frequency(self, simple_repo: Path) -> None:
        result = FileScanner().scan(simple_repo)
        counts = list(result.extension_counts.values())
        assert counts == sorted(counts, reverse=True)

    def test_total_size_bytes(self, simple_repo: Path) -> None:
        result = FileScanner().scan(simple_repo)
        assert result.total_size_bytes > 0
        manual = sum(f.size_bytes for f in result.files)
        assert result.total_size_bytes == manual


# ---------------------------------------------------------------------------
# FileScanner.scan — happy path
# ---------------------------------------------------------------------------


class TestFileScannerHappyPath:
    def test_returns_scan_result(self, simple_repo: Path) -> None:
        result = FileScanner().scan(simple_repo)
        assert isinstance(result, ScanResult)

    def test_root_is_resolved(self, simple_repo: Path) -> None:
        result = FileScanner().scan(simple_repo)
        assert result.root == simple_repo.resolve()

    def test_accepts_string_path(self, simple_repo: Path) -> None:
        result = FileScanner().scan(str(simple_repo))
        assert result.file_count == 7

    def test_discovers_nested_files(self, simple_repo: Path) -> None:
        result = FileScanner().scan(simple_repo)
        rel_paths = {str(f.relative_path) for f in result.files}
        assert "src/app.py" in rel_paths or "src\\app.py" in rel_paths
        assert any("helpers" in p for p in rel_paths)

    def test_no_errors_on_clean_repo(self, simple_repo: Path) -> None:
        result = FileScanner().scan(simple_repo)
        assert result.errors == []

    def test_ignored_dirs_recorded(self, repo_with_ignored: Path) -> None:
        result = FileScanner().scan(repo_with_ignored)
        ignored_names = {Path(d).parts[0] for d in result.ignored_dirs}
        assert ".git" in ignored_names
        assert "__pycache__" in ignored_names
        assert "node_modules" in ignored_names
        assert "venv" in ignored_names
        assert ".venv" in ignored_names

    def test_files_in_ignored_dirs_excluded(self, repo_with_ignored: Path) -> None:
        result = FileScanner().scan(repo_with_ignored)
        for entry in result.files:
            parts = entry.relative_path.parts
            assert ".git" not in parts
            assert "__pycache__" not in parts
            assert "node_modules" not in parts

    def test_real_subdirs_not_ignored(self, repo_with_ignored: Path) -> None:
        result = FileScanner().scan(repo_with_ignored)
        rel_paths = {str(f.relative_path) for f in result.files}
        assert any("mypackage" in p for p in rel_paths)

    def test_egg_info_ignored(self, tmp_path: Path) -> None:
        egg = tmp_path / "myproject.egg-info"
        egg.mkdir()
        (egg / "PKG-INFO").write_text("Name: myproject")
        (tmp_path / "setup.py").write_text("pass")

        result = FileScanner().scan(tmp_path)
        for entry in result.files:
            assert "egg-info" not in str(entry.relative_path)

    def test_empty_directory(self, tmp_path: Path) -> None:
        result = FileScanner().scan(tmp_path)
        assert result.file_count == 0
        assert result.errors == []


# ---------------------------------------------------------------------------
# FileScanner.scan — error handling
# ---------------------------------------------------------------------------


class TestFileScannerErrors:
    def test_nonexistent_path(self) -> None:
        with pytest.raises(ScanError, match="does not exist"):
            FileScanner().scan("/nonexistent/path/that/cannot/exist/abc123")

    def test_file_path_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("content")
        with pytest.raises(ScanError, match="file, not a directory"):
            FileScanner().scan(f)

    @pytest.mark.skipif(sys.platform == "win32", reason="chmod restricted dirs behave differently on Windows")
    def test_permission_error_on_subdir(self, tmp_path: Path) -> None:
        locked = tmp_path / "locked"
        locked.mkdir()
        (locked / "secret.py").write_text("pass")
        locked.chmod(0o000)

        try:
            result = FileScanner().scan(tmp_path)
            assert any("locked" in e for e in result.errors)
        finally:
            locked.chmod(stat.S_IRWXU)


# ---------------------------------------------------------------------------
# Custom ignore_dirs
# ---------------------------------------------------------------------------


class TestCustomIgnoreDirs:
    def test_custom_ignore_set(self, tmp_path: Path) -> None:
        skip = tmp_path / "skip_me"
        skip.mkdir()
        (skip / "stuff.py").write_text("pass")
        (tmp_path / "keep.py").write_text("pass")

        result = FileScanner(ignore_dirs=frozenset({"skip_me"})).scan(tmp_path)
        rel_paths = {str(f.relative_path) for f in result.files}
        assert "keep.py" in rel_paths
        assert not any("skip_me" in p for p in rel_paths)


# ---------------------------------------------------------------------------
# CLI scan command
# ---------------------------------------------------------------------------


class TestScanCLI:
    def test_scan_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["scan", "--help"])
        assert result.exit_code == 0
        assert "--format" in result.output
        assert "--top" in result.output

    def test_scan_text_output(self, simple_repo: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["scan", str(simple_repo)])
        assert result.exit_code == 0
        assert "7" in result.output  # file count
        assert ".py" in result.output

    def test_scan_json_output(self, simple_repo: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["scan", "--format", "json", str(simple_repo)])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["file_count"] == 7
        assert ".py" in payload["extension_counts"]
        assert "root" in payload
        assert "ignored_dirs" in payload

    def test_scan_invalid_path(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["scan", "/no/such/directory/xyz"])
        assert result.exit_code != 0

    def test_scan_ignored_dirs_reported(self, repo_with_ignored: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["scan", str(repo_with_ignored)])
        assert result.exit_code == 0
        assert "Ignored" in result.output

    def test_scan_top_flag(self, simple_repo: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["scan", "--top", "2", str(simple_repo)])
        assert result.exit_code == 0
        assert "Top 2" in result.output

    def test_scan_defaults_to_cwd(self, simple_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(simple_repo)
        runner = CliRunner()
        result = runner.invoke(cli, ["scan"])
        assert result.exit_code == 0
