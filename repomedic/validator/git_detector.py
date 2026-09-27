"""GitChangesDetector — detect changed files in a Git repository.

Uses ``git diff --name-only`` to enumerate files modified relative to
the current working tree.  Falls back gracefully when the directory is
not a Git repository or when ``git`` is not available.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitChangesDetector:
    """Detect changed files in a Git repository.

    Parameters
    ----------
    repo_root:
        Path to the repository root to inspect.
    """

    def __init__(self, repo_root: Path) -> None:
        self._root = repo_root

    def is_git_repo(self) -> bool:
        """Return True if *repo_root* is inside a Git repository."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=str(self._root),
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0 and result.stdout.strip() == "true"
        except (OSError, subprocess.TimeoutExpired):
            return False

    def changed_files(self) -> list[str]:
        """Return a list of repository-relative paths for changed files.

        Combines staged changes (``--cached``), unstaged changes, and
        untracked files so that the caller gets the full working-tree diff.

        Returns an empty list if the directory is not a Git repository,
        if ``git`` is not installed, or on any other error.
        """
        if not self.is_git_repo():
            return []

        paths: set[str] = set()

        # Staged changes
        paths.update(self._run_git_diff("--cached"))
        # Unstaged changes
        paths.update(self._run_git_diff())
        # Untracked files
        paths.update(self._run_git_ls_files_others())

        return sorted(paths)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_git_diff(self, *extra_args: str) -> list[str]:
        """Run ``git diff --name-only [extra_args]`` and return the file list."""
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", *extra_args],
                cwd=str(self._root),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return []
            return [line for line in result.stdout.splitlines() if line.strip()]
        except (OSError, subprocess.TimeoutExpired):
            return []

    def _run_git_ls_files_others(self) -> list[str]:
        """Return untracked files via ``git ls-files --others --exclude-standard``."""
        try:
            result = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=str(self._root),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return []
            return [line for line in result.stdout.splitlines() if line.strip()]
        except (OSError, subprocess.TimeoutExpired):
            return []
