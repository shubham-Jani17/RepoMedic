"""Fixing subsystem — propose, apply, and verify repository fixes.

Public API
----------
FixSuggestion       — proposed change (no FS side-effects)
FixKind             — kind of operation a fix would perform
FixResult           — outcome of applying one FixSuggestion
FixStatus           — CREATED / SKIPPED / ERROR
ApplyReport         — aggregated result of an AutoFixer run
IssueResolution     — whether a specific issue was resolved
VerificationResult  — outcome of re-analysing after fixes

PatchGenerator      — translate analysis issues → FixSuggestion objects
AutoFixer           — safely apply FixSuggestions to the filesystem
FixVerifier         — re-analyse and confirm resolution
"""

from repomedic.fixer.auto_fixer import AutoFixer
from repomedic.fixer.models import (
    ApplyReport,
    FixKind,
    FixResult,
    FixStatus,
    FixSuggestion,
    IssueResolution,
    VerificationResult,
)
from repomedic.fixer.patch_generator import PatchGenerator
from repomedic.fixer.verifier import FixVerifier

__all__ = [
    # models
    "ApplyReport",
    "FixKind",
    "FixResult",
    "FixStatus",
    "FixSuggestion",
    "IssueResolution",
    "VerificationResult",
    # pipeline components
    "AutoFixer",
    "FixVerifier",
    "PatchGenerator",
]
