"""Validator subsystem — repository validation and CI/CD gate.

Public API
----------
GitChangesDetector   — detect changed files via Git
RepositoryValidator  — full validation pipeline
ValidationResult     — result model
"""

from repomedic.validator.git_detector import GitChangesDetector
from repomedic.validator.models import ValidationResult
from repomedic.validator.validator import RepositoryValidator

__all__ = [
    "GitChangesDetector",
    "RepositoryValidator",
    "ValidationResult",
]
