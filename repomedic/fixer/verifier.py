"""FixVerifier — re-analyse a repository after fixes and confirm resolution.

Workflow
--------
1. Record the set of issue IDs that were targeted by the applied fixes.
2. Re-run the full scanner → detector → analysis pipeline on the same root.
3. For each targeted issue, check whether an issue with the same title and
   category is still present in the new analysis.
4. Count any *new* issues that were not present before the fix.
5. Return a :class:`~repomedic.fixer.models.VerificationResult`.
"""

from __future__ import annotations

from pathlib import Path

from repomedic.analyzer.engine import AnalysisEngine
from repomedic.analyzer.models import AnalysisResult, Issue
from repomedic.fixer.models import (
    ApplyReport,
    IssueResolution,
    VerificationResult,
)
from repomedic.scanner.file_scanner import FileScanner
from repomedic.scanner.project_detector import ProjectDetector


class FixVerifier:
    """Re-analyse a repository and verify that targeted issues were resolved.

    Parameters
    ----------
    repo_root:
        Absolute path to the repository root.
    """

    def __init__(self, repo_root: Path) -> None:
        self._root = repo_root.resolve()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def verify(
        self,
        before: AnalysisResult,
        report: ApplyReport,
    ) -> VerificationResult:
        """Verify fixes by re-running the analysis pipeline.

        Parameters
        ----------
        before:
            The :class:`~repomedic.analyzer.models.AnalysisResult` produced
            **before** any fixes were applied.
        report:
            The :class:`~repomedic.fixer.models.ApplyReport` from the
            :class:`~repomedic.fixer.auto_fixer.AutoFixer` run.

        Returns
        -------
        VerificationResult
            One :class:`~repomedic.fixer.models.IssueResolution` entry for
            every issue that was targeted by a fix that reached CREATED status.
        """
        # Only verify issues that were actually created (not skipped/errored).
        targeted_ids = {
            r.suggestion.issue_id
            for r in report.created
        }

        if not targeted_ids:
            return VerificationResult()

        # Find the original issues we targeted.
        targeted_issues = [i for i in before.issues if i.issue_id in targeted_ids]

        # Re-run the full analysis pipeline.
        after = self._reanalyse()

        # Build a lookup of (title_lower, category) pairs still present.
        still_present = {
            (i.title.lower(), i.category)
            for i in after.issues
        }

        resolutions: list[IssueResolution] = []
        for issue in targeted_issues:
            key = (issue.title.lower(), issue.category)
            resolved = key not in still_present
            resolutions.append(
                IssueResolution(
                    issue_id=issue.issue_id,
                    issue_title=issue.title,
                    resolved=resolved,
                )
            )

        # Count issues that are genuinely new (not present before the fix).
        before_keys = {(i.title.lower(), i.category) for i in before.issues}
        after_keys = {(i.title.lower(), i.category) for i in after.issues}
        new_issues_count = len(after_keys - before_keys)

        return VerificationResult(
            resolutions=resolutions,
            new_issues_count=new_issues_count,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _reanalyse(self) -> AnalysisResult:
        """Perform a fresh scan → detect → analyse cycle."""
        scan_result = FileScanner().scan(self._root)
        proj_result = ProjectDetector().detect(scan_result)
        return AnalysisEngine().run(scan_result, proj_result)
