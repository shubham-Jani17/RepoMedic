"""Data models for the validation subsystem."""

from __future__ import annotations

import dataclasses
from pathlib import Path


@dataclasses.dataclass
class ValidationResult:
    """Outcome of a full repository validation run.

    Attributes
    ----------
    repo_root:
        Absolute path to the repository root.
    health_score:
        Computed health score (0–100).
    threshold:
        Minimum acceptable score supplied by the caller (default 0 = no threshold).
    blocking_errors:
        Critical/blocking issues that force FAIL regardless of score.
    is_git_repo:
        Whether the repository is a Git repository.
    changed_files:
        Files reported as changed by Git (empty for non-Git repos).
    affected_files:
        Downstream files transitively affected by the changed files.
    blast_radius:
        Total number of files in the blast radius.
    passed:
        Final PASS / FAIL verdict.
    """

    repo_root: Path
    health_score: int = 100
    threshold: int = 0
    blocking_errors: list[str] = dataclasses.field(default_factory=list)
    is_git_repo: bool = False
    changed_files: list[str] = dataclasses.field(default_factory=list)
    affected_files: list[str] = dataclasses.field(default_factory=list)
    blast_radius: int = 0
    passed: bool = True

    def as_dict(self) -> dict:
        return {
            "repo_root": str(self.repo_root),
            "health_score": self.health_score,
            "threshold": self.threshold,
            "blocking_errors": self.blocking_errors,
            "is_git_repo": self.is_git_repo,
            "changed_files": self.changed_files,
            "affected_files": self.affected_files,
            "blast_radius": self.blast_radius,
            "passed": self.passed,
        }
