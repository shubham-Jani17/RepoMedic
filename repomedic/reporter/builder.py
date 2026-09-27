"""ReportBuilder — assemble a ReportData from pipeline outputs.

This is the glue layer that turns raw scanner / detector / analysis
outputs into the intermediate :class:`~repomedic.reporter.models.ReportData`
that reporters consume.
"""

from __future__ import annotations

from repomedic.analyzer.models import AnalysisResult, Category
from repomedic.reporter.health_score import HealthScoreCalculator
from repomedic.reporter.models import ReportData
from repomedic.scanner.language_detector import LanguageDetectionResult
from repomedic.scanner.models import ScanResult
from repomedic.scanner.project_detector import ProjectDetectionResult

_CALC = HealthScoreCalculator()


class ReportBuilder:
    """Construct a :class:`~repomedic.reporter.models.ReportData`.

    Usage::

        builder = ReportBuilder(scan, proj, lang, analysis)
        data = builder.build()
    """

    def __init__(
        self,
        scan: ScanResult,
        project: ProjectDetectionResult,
        lang: LanguageDetectionResult,
        analysis: AnalysisResult,
    ) -> None:
        self._scan = scan
        self._project = project
        self._lang = lang
        self._analysis = analysis

    def build(self) -> ReportData:
        score = _CALC.score(self._analysis)
        status = _CALC.status(score)

        governance_status = self._governance_status()
        verification_status = "not_run"

        issues = [i.as_dict() for i in self._analysis.issues]

        return ReportData(
            repo_root=self._scan.root,
            project_types=list(self._project.project_types),
            languages=[s.name for s in self._lang.languages],
            health_score=score,
            status=status,
            total_issues=len(self._analysis.issues),
            total_errors=len(self._analysis.errors),
            total_warnings=len(self._analysis.warnings),
            verification_status=verification_status,
            governance_status=governance_status,
            issues=issues,
            errors=list(self._analysis.errors),
            warnings=list(self._analysis.warnings),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _governance_status(self) -> str:
        gov_issues = [
            i for i in self._analysis.issues if i.category == Category.GOVERNANCE
        ]
        if not gov_issues:
            return "ok"
        return "missing_files"
