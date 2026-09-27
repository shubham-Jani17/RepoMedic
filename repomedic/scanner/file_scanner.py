"""FileScanner — recursively discovers files in a repository."""

from __future__ import annotations

import os
from pathlib import Path

from repomedic.scanner.models import FileEntry, ScanResult

# Directories that are never worth scanning
DEFAULT_IGNORE_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        "__pycache__",
        ".pytest_cache",
        "node_modules",
        "venv",
        "env",
        ".venv",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        "dist",
        "build",
        ".eggs",
        "*.egg-info",
    }
)


class ScanError(Exception):
    """Raised when the scan cannot proceed due to an unrecoverable input error."""


class FileScanner:
    """Recursively scan a directory tree and collect file metadata.

    Parameters
    ----------
    ignore_dirs:
        Set of directory *names* (not full paths) to skip entirely.
        Defaults to :data:`DEFAULT_IGNORE_DIRS`.
    """

    def __init__(self, ignore_dirs: frozenset[str] | None = None) -> None:
        self.ignore_dirs: frozenset[str] = (
            ignore_dirs if ignore_dirs is not None else DEFAULT_IGNORE_DIRS
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self, path: str | Path) -> ScanResult:
        """Scan *path* and return a :class:`ScanResult`.

        Raises
        ------
        ScanError
            If *path* does not exist, is not a directory, or cannot be read.
        """
        root = self._validate_path(path)
        result = ScanResult(root=root)
        self._walk(root, root, result)
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_path(path: str | Path) -> Path:
        p = Path(path).resolve()
        if not p.exists():
            raise ScanError(f"Path does not exist: {p}")
        if p.is_file():
            raise ScanError(
                f"Path is a file, not a directory: {p}\n"
                "Provide the root directory of the repository."
            )
        if not p.is_dir():
            raise ScanError(f"Path is not a directory: {p}")
        if not os.access(p, os.R_OK):
            raise ScanError(f"Permission denied: {p}")
        return p

    def _should_ignore_dir(self, dir_name: str) -> bool:
        """Return True if *dir_name* matches any ignored pattern."""
        if dir_name in self.ignore_dirs:
            return True
        # Support simple glob suffix patterns like "*.egg-info"
        for pattern in self.ignore_dirs:
            if pattern.startswith("*") and dir_name.endswith(pattern[1:]):
                return True
        return False

    def _walk(self, current: Path, root: Path, result: ScanResult) -> None:
        try:
            entries = list(current.iterdir())
        except PermissionError as exc:
            result.errors.append(f"Permission denied: {current} ({exc})")
            return

        for entry in sorted(entries, key=lambda e: (e.is_file(), e.name)):
            # Avoid following symlinks — check for symlink before is_dir/is_file
            # (follow_symlinks kwarg on Path methods requires Python 3.12+)
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if self._should_ignore_dir(entry.name):
                    result.ignored_dirs.append(str(entry.relative_to(root)))
                else:
                    self._walk(entry, root, result)
            elif entry.is_file():
                try:
                    result.files.append(FileEntry.from_path(entry, root))
                except PermissionError as exc:
                    result.errors.append(f"Permission denied reading file: {entry} ({exc})")
                except OSError as exc:
                    result.errors.append(f"OS error reading file: {entry} ({exc})")
