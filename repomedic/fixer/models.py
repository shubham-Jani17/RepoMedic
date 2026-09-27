"""Data models for the fixing subsystem.

FixSuggestion      — a proposed change, with no filesystem side-effects
FixResult          — outcome of applying one FixSuggestion
ApplyReport        — aggregated result of an AutoFixer run
VerificationResult — outcome of re-analysing after fixes were applied
"""

from __future__ import annotations

import dataclasses
import enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# FixSuggestion — a proposed change (read-only description)
# ---------------------------------------------------------------------------


class FixKind(enum.Enum):
    """Kind of filesystem operation a fix would perform."""

    CREATE_FILE = "create_file"   # create a new file (safe: no overwrite)


@dataclasses.dataclass
class FixSuggestion:
    """A proposed change to the repository.

    A ``FixSuggestion`` is purely descriptive — it carries no side-effects.
    Creating one does *not* touch the filesystem.

    Parameters
    ----------
    issue_id:
        The ``Issue.issue_id`` this suggestion addresses.
    issue_title:
        Human-readable title of the issue (copied for display convenience).
    kind:
        What kind of operation would be performed.
    target_path:
        Repository-relative path of the file to create.
    content:
        Content that would be written to *target_path*.
    rationale:
        One-sentence explanation of why this fix helps.
    """

    issue_id: str
    issue_title: str
    kind: FixKind
    target_path: Path   # repository-relative
    content: str
    rationale: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "issue_title": self.issue_title,
            "kind": self.kind.value,
            "target_path": str(self.target_path),
            "content_preview": self.content[:120] + ("…" if len(self.content) > 120 else ""),
            "rationale": self.rationale,
        }


# ---------------------------------------------------------------------------
# FixStatus — outcome of applying a single fix
# ---------------------------------------------------------------------------


class FixStatus(enum.Enum):
    CREATED = "created"     # file was created successfully
    SKIPPED = "skipped"     # file already existed — left untouched
    ERROR = "error"         # filesystem error prevented the operation


@dataclasses.dataclass
class FixResult:
    """Outcome of applying one :class:`FixSuggestion`.

    Parameters
    ----------
    suggestion:
        The suggestion that was (or was attempted to be) applied.
    status:
        Whether the fix was created, skipped, or failed.
    message:
        Human-readable detail; always set for SKIPPED and ERROR statuses.
    """

    suggestion: FixSuggestion
    status: FixStatus
    message: str = ""

    @property
    def ok(self) -> bool:
        """True when the operation succeeded (CREATED or SKIPPED)."""
        return self.status in (FixStatus.CREATED, FixStatus.SKIPPED)

    def as_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.suggestion.issue_id,
            "issue_title": self.suggestion.issue_title,
            "target_path": str(self.suggestion.target_path),
            "status": self.status.value,
            "message": self.message,
        }


# ---------------------------------------------------------------------------
# ApplyReport — aggregated result of an AutoFixer run
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class ApplyReport:
    """Aggregated outcome of applying a set of :class:`FixSuggestion` objects.

    Parameters
    ----------
    results:
        One :class:`FixResult` per suggestion that was processed.
    """

    results: list[FixResult] = dataclasses.field(default_factory=list)

    @property
    def created(self) -> list[FixResult]:
        return [r for r in self.results if r.status == FixStatus.CREATED]

    @property
    def skipped(self) -> list[FixResult]:
        return [r for r in self.results if r.status == FixStatus.SKIPPED]

    @property
    def errors(self) -> list[FixResult]:
        return [r for r in self.results if r.status == FixStatus.ERROR]

    @property
    def all_ok(self) -> bool:
        return all(r.ok for r in self.results)

    def as_dict(self) -> dict[str, Any]:
        return {
            "created_count": len(self.created),
            "skipped_count": len(self.skipped),
            "error_count": len(self.errors),
            "results": [r.as_dict() for r in self.results],
        }


# ---------------------------------------------------------------------------
# VerificationResult — re-analysis outcome after fixes
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class IssueResolution:
    """Tracks whether a specific issue was resolved after fixes were applied."""

    issue_id: str
    issue_title: str
    resolved: bool   # True if issue no longer appears in the re-analysis

    def as_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "issue_title": self.issue_title,
            "resolved": self.resolved,
        }


@dataclasses.dataclass
class VerificationResult:
    """Outcome of re-analysing a repository after fixes were applied.

    Parameters
    ----------
    resolutions:
        One entry per issue that was targeted by a fix.
    new_issues_count:
        Number of issues present *after* fixing that were *not* present before.
        Should be 0 for safe governance fixes.
    """

    resolutions: list[IssueResolution] = dataclasses.field(default_factory=list)
    new_issues_count: int = 0

    @property
    def all_resolved(self) -> bool:
        return bool(self.resolutions) and all(r.resolved for r in self.resolutions)

    @property
    def resolved_count(self) -> int:
        return sum(1 for r in self.resolutions if r.resolved)

    @property
    def unresolved_count(self) -> int:
        return sum(1 for r in self.resolutions if not r.resolved)

    def as_dict(self) -> dict[str, Any]:
        return {
            "all_resolved": self.all_resolved,
            "resolved_count": self.resolved_count,
            "unresolved_count": self.unresolved_count,
            "new_issues_count": self.new_issues_count,
            "resolutions": [r.as_dict() for r in self.resolutions],
        }
