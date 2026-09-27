"""AutoFixer — safely apply :class:`~repomedic.fixer.models.FixSuggestion` objects.

Safety guarantees
-----------------
* **Never overwrites an existing file.**  If the target already exists the fix
  is recorded as :attr:`~repomedic.fixer.models.FixStatus.SKIPPED`.
* **Never deletes files.**  The only supported operation is
  :attr:`~repomedic.fixer.models.FixKind.CREATE_FILE`.
* **Never modifies arbitrary source code.**  Only governance boilerplate files
  (.gitignore, README.md, LICENSE) are created.
* **Reports exactly what happened** — every outcome (CREATED / SKIPPED / ERROR)
  is captured in a :class:`~repomedic.fixer.models.FixResult`.
* **Handles filesystem errors gracefully** — ``OSError`` / ``PermissionError``
  are caught and recorded as ERROR results; the run continues.
"""

from __future__ import annotations

from pathlib import Path

from repomedic.fixer.models import (
    ApplyReport,
    FixKind,
    FixResult,
    FixStatus,
    FixSuggestion,
)


class AutoFixer:
    """Apply a list of :class:`~repomedic.fixer.models.FixSuggestion` objects
    to a repository.

    Parameters
    ----------
    repo_root:
        Absolute path to the repository root.  All
        ``suggestion.target_path`` values are resolved relative to this
        directory.
    dry_run:
        When ``True``, simulate the operation without touching the
        filesystem.  Every suggestion that *would* succeed is recorded as
        CREATED; suggestions blocked by an existing file are still SKIPPED.
    """

    def __init__(self, repo_root: Path, *, dry_run: bool = False) -> None:
        self._root = repo_root.resolve()
        self._dry_run = dry_run

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply(self, suggestions: list[FixSuggestion]) -> ApplyReport:
        """Apply *suggestions* and return an :class:`~repomedic.fixer.models.ApplyReport`.

        Each suggestion is processed independently.  A failure on one does
        not abort the remaining suggestions.
        """
        report = ApplyReport()
        for suggestion in suggestions:
            result = self._apply_one(suggestion)
            report.results.append(result)
        return report

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_one(self, suggestion: FixSuggestion) -> FixResult:
        if suggestion.kind != FixKind.CREATE_FILE:
            # Only CREATE_FILE is supported; reject anything else explicitly
            kind_repr = (
                suggestion.kind.value
                if isinstance(suggestion.kind, FixKind)
                else repr(suggestion.kind)
            )
            return FixResult(
                suggestion=suggestion,
                status=FixStatus.ERROR,
                message=(
                    f"Unsupported fix kind: {kind_repr!r}. "
                    "AutoFixer only supports CREATE_FILE operations."
                ),
            )

        target: Path = self._root / suggestion.target_path

        # Safety check: never overwrite an existing file
        if target.exists():
            return FixResult(
                suggestion=suggestion,
                status=FixStatus.SKIPPED,
                message=f"File already exists — left untouched: {suggestion.target_path}",
            )

        if self._dry_run:
            return FixResult(
                suggestion=suggestion,
                status=FixStatus.CREATED,
                message=f"[dry-run] Would create: {suggestion.target_path}",
            )

        # Attempt to write the file
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(suggestion.content, encoding="utf-8")
        except PermissionError as exc:
            return FixResult(
                suggestion=suggestion,
                status=FixStatus.ERROR,
                message=f"Permission denied writing {suggestion.target_path}: {exc}",
            )
        except OSError as exc:
            return FixResult(
                suggestion=suggestion,
                status=FixStatus.ERROR,
                message=f"OS error writing {suggestion.target_path}: {exc}",
            )

        return FixResult(
            suggestion=suggestion,
            status=FixStatus.CREATED,
            message=f"Created: {suggestion.target_path}",
        )
