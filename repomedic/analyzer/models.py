"""Core data models for analysis findings."""

from __future__ import annotations

import dataclasses
import enum
import uuid
from pathlib import Path


# ---------------------------------------------------------------------------
# Severity
# ---------------------------------------------------------------------------


class Severity(enum.Enum):
    """Ordered severity levels for analysis issues."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    # Allow numeric comparison: CRITICAL > HIGH > … > INFO
    def __lt__(self, other: "Severity") -> bool:
        return _SEVERITY_ORDER[self] < _SEVERITY_ORDER[other]

    def __le__(self, other: "Severity") -> bool:
        return _SEVERITY_ORDER[self] <= _SEVERITY_ORDER[other]

    def __gt__(self, other: "Severity") -> bool:
        return _SEVERITY_ORDER[self] > _SEVERITY_ORDER[other]

    def __ge__(self, other: "Severity") -> bool:
        return _SEVERITY_ORDER[self] >= _SEVERITY_ORDER[other]


_SEVERITY_ORDER: dict[Severity, int] = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}

# Terminal colour codes used when rendering issues
SEVERITY_COLOURS: dict[Severity, str] = {
    Severity.INFO: "\033[36m",      # cyan
    Severity.LOW: "\033[34m",       # blue
    Severity.MEDIUM: "\033[33m",    # yellow
    Severity.HIGH: "\033[31m",      # red
    Severity.CRITICAL: "\033[35m",  # magenta
}

# Short display labels (fixed width for aligned output)
SEVERITY_LABELS: dict[Severity, str] = {
    Severity.INFO: "INFO    ",
    Severity.LOW: "LOW     ",
    Severity.MEDIUM: "MEDIUM  ",
    Severity.HIGH: "HIGH    ",
    Severity.CRITICAL: "CRITICAL",
}


# ---------------------------------------------------------------------------
# Issue category
# ---------------------------------------------------------------------------


class Category(enum.Enum):
    """Broad category of an analysis issue."""

    SYNTAX = "syntax"
    GOVERNANCE = "governance"
    DEPENDENCY = "dependency"
    SECURITY = "security"
    STYLE = "style"
    ERROR = "error"
    OTHER = "other"


# ---------------------------------------------------------------------------
# Issue
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class Issue:
    """A single finding produced by an analyzer.

    Parameters
    ----------
    title:
        Short human-readable title.
    severity:
        How serious the issue is.
    category:
        Broad issue category.
    description:
        Full explanation of the problem.
    recommendation:
        What to do to fix or address it.
    file:
        Repository-relative path of the affected file, if applicable.
    line:
        Line number within *file*, if applicable (1-based).
    issue_id:
        Stable unique identifier.  Auto-generated if not supplied.
    """

    title: str
    severity: Severity
    category: Category
    description: str
    recommendation: str
    file: Path | None = None
    line: int | None = None
    issue_id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4())[:8])

    def as_dict(self) -> dict:
        return {
            "issue_id": self.issue_id,
            "title": self.title,
            "severity": self.severity.value,
            "category": self.category.value,
            "file": str(self.file) if self.file else None,
            "line": self.line,
            "description": self.description,
            "recommendation": self.recommendation,
        }


# ---------------------------------------------------------------------------
# AnalysisResult
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class AnalysisResult:
    """Aggregated output of a full analysis run.

    Parameters
    ----------
    root:
        Resolved path of the scanned repository root.
    issues:
        All findings from every analyzer, sorted by severity descending.
    errors:
        Internal errors that prevented an analyzer from completing (e.g.
        permission denied).
    warnings:
        Non-fatal notices about the analysis run itself.
    """

    root: Path
    issues: list[Issue] = dataclasses.field(default_factory=list)
    errors: list[str] = dataclasses.field(default_factory=list)
    warnings: list[str] = dataclasses.field(default_factory=list)

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    def by_severity(self, severity: Severity) -> list[Issue]:
        """Return all issues with exactly *severity*."""
        return [i for i in self.issues if i.severity == severity]

    def by_category(self, category: Category) -> list[Issue]:
        """Return all issues in *category*."""
        return [i for i in self.issues if i.category == category]

    @property
    def has_critical(self) -> bool:
        return any(i.severity == Severity.CRITICAL for i in self.issues)

    @property
    def has_high(self) -> bool:
        return any(i.severity == Severity.HIGH for i in self.issues)

    def severity_counts(self) -> dict[str, int]:
        """Return a mapping of severity label → count."""
        counts: dict[str, int] = {s.value: 0 for s in Severity}
        for issue in self.issues:
            counts[issue.severity.value] += 1
        return counts

    def sort_issues(self) -> None:
        """Sort issues in-place: highest severity first, then by file + line."""
        self.issues.sort(
            key=lambda i: (
                -_SEVERITY_ORDER[i.severity],
                str(i.file or ""),
                i.line or 0,
            )
        )
