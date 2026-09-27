"""Intermediate data model for the reporting subsystem.

ReportData aggregates all the information needed to produce either a
terminal or JSON report without the reporters having to re-run any
analysis themselves.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any


@dataclasses.dataclass
class ReportData:
    """All data a reporter needs to produce its output.

    Parameters
    ----------
    repo_root:
        Absolute path to the repository root.
    project_types:
        Detected project types (e.g. ``["Python", "Docker"]``).
    languages:
        Detected language names ordered by prevalence.
    health_score:
        Integer 0–100 computed by :class:`~repomedic.reporter.health_score.HealthScoreCalculator`.
    status:
        Human-readable status label derived from the score
        (``"healthy"`` / ``"warning"`` / ``"error"``).
    total_issues:
        Total number of issues found by all analyzers.
    total_errors:
        Number of internal analysis errors (analyzer failures, not code issues).
    total_warnings:
        Number of analysis warnings (non-fatal, e.g. unreadable files).
    verification_status:
        Overall verification conclusion:
        ``"passed"`` / ``"failed"`` / ``"not_run"``.
    governance_status:
        Summary of governance checks:
        ``"ok"`` / ``"warnings"`` / ``"missing_files"``.
    issues:
        All findings from every analyzer, sorted by severity descending.
    errors:
        Internal analyzer error strings.
    warnings:
        Non-fatal analyzer warning strings.
    """

    repo_root: Path
    project_types: list[str] = dataclasses.field(default_factory=list)
    languages: list[str] = dataclasses.field(default_factory=list)
    health_score: int = 100
    status: str = "healthy"
    total_issues: int = 0
    total_errors: int = 0
    total_warnings: int = 0
    verification_status: str = "not_run"
    governance_status: str = "ok"

    issues: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    errors: list[str] = dataclasses.field(default_factory=list)
    warnings: list[str] = dataclasses.field(default_factory=list)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def as_dict(self) -> dict[str, Any]:
        """Return the full report as a plain Python dictionary.

        This is the canonical structure used by :class:`JSONReporter`.
        """
        return {
            "repository": str(self.repo_root),
            "status": self.status,
            "health_score": self.health_score,
            "total_issues": self.total_issues,
            "total_errors": self.total_errors,
            "total_warnings": self.total_warnings,
            "project_types": self.project_types,
            "languages": self.languages,
            "verification_status": self.verification_status,
            "governance_status": self.governance_status,
            "errors": self.errors,
            "warnings": self.warnings,
            "issues": self.issues,
        }
