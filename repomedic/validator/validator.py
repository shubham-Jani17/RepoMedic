"""RepositoryValidator — orchestrates the full validation pipeline.

Validation workflow
-------------------
1. Scan the repository (FileScanner)
2. Detect project structure (ProjectDetector)
3. Run all analyzers (AnalysisEngine)
4. Compute health score (HealthScoreCalculator)
5. Detect Git changes (GitChangesDetector)
6. Build dependency graph (build_graph_from_scan)
7. Compute blast radius for changed files (BlastRadiusAnalyzer)
8. Determine PASS / FAIL verdict

The repository FAILs when:
- health score is below the threshold, OR
- blocking errors (CRITICAL-severity issues) are detected.
"""

from __future__ import annotations

from pathlib import Path

from repomedic.analyzer import AnalysisEngine, Severity
from repomedic.graph import BlastRadiusAnalyzer, build_graph_from_scan
from repomedic.reporter import HealthScoreCalculator
from repomedic.scanner import FileScanner, LanguageDetector, ProjectDetector, ScanError
from repomedic.validator.git_detector import GitChangesDetector
from repomedic.validator.models import ValidationResult


class RepositoryValidator:
    """Run the full validation pipeline against a repository.

    Parameters
    ----------
    threshold:
        Minimum health score for the repository to PASS.
        A score strictly below this value causes FAIL.
        Defaults to 0 (no threshold — only blocking errors can cause FAIL).
    """

    def __init__(self, threshold: int = 0) -> None:
        self._threshold = threshold

    def validate(self, path: str | Path) -> ValidationResult:
        """Run the validation pipeline and return a :class:`ValidationResult`.

        Parameters
        ----------
        path:
            Repository root directory.

        Raises
        ------
        ScanError
            If the directory cannot be scanned (e.g. does not exist).
        """
        root = Path(path).resolve()

        # ------------------------------------------------------------------
        # 1–3. Scan → detect → analyze
        # ------------------------------------------------------------------
        scan_result = FileScanner().scan(str(root))
        proj_result = ProjectDetector().detect(scan_result)
        analysis = AnalysisEngine().run(scan_result, proj_result)

        # ------------------------------------------------------------------
        # 4. Health score
        # ------------------------------------------------------------------
        calc = HealthScoreCalculator()
        health_score = calc.score(analysis)

        # ------------------------------------------------------------------
        # 5. Git changes
        # ------------------------------------------------------------------
        git = GitChangesDetector(root)
        is_git = git.is_git_repo()
        changed_files = git.changed_files() if is_git else []

        # ------------------------------------------------------------------
        # 6–7. Dependency graph + blast radius
        # ------------------------------------------------------------------
        affected_files: list[str] = []
        blast_radius = 0

        if changed_files:
            dep_graph = build_graph_from_scan(scan_result)
            br_result = BlastRadiusAnalyzer(dep_graph).analyze(changed_files)
            affected_files = br_result.sorted_affected()
            blast_radius = br_result.total_affected

        # ------------------------------------------------------------------
        # 8. Blocking errors: any CRITICAL issue
        # ------------------------------------------------------------------
        blocking_errors = [
            f"[{i.issue_id}] {i.title}"
            for i in analysis.issues
            if i.severity == Severity.CRITICAL
        ]

        # ------------------------------------------------------------------
        # 9. Verdict
        # ------------------------------------------------------------------
        passed = (health_score >= self._threshold) and (not blocking_errors)

        return ValidationResult(
            repo_root=root,
            health_score=health_score,
            threshold=self._threshold,
            blocking_errors=blocking_errors,
            is_git_repo=is_git,
            changed_files=changed_files,
            affected_files=affected_files,
            blast_radius=blast_radius,
            passed=passed,
        )
