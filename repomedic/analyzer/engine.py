"""AnalysisEngine — orchestrates all analyzers and collects results."""

from __future__ import annotations

from pathlib import Path

from repomedic.analyzer.base import Analyzer
from repomedic.analyzer.dependency import DependencyAnalyzer
from repomedic.analyzer.error import ErrorAnalyzer
from repomedic.analyzer.governance import GovernanceAnalyzer
from repomedic.analyzer.models import AnalysisResult
from repomedic.analyzer.syntax import SyntaxAnalyzer
from repomedic.scanner.models import ScanResult
from repomedic.scanner.project_detector import ProjectDetectionResult

# Default set of analyzers run in declaration order.
DEFAULT_ANALYZERS: list[Analyzer] = [
    SyntaxAnalyzer(),   # type: ignore[list-item]
    GovernanceAnalyzer(),  # type: ignore[list-item]
    DependencyAnalyzer(),  # type: ignore[list-item]
    ErrorAnalyzer(),    # type: ignore[list-item]
]


class AnalysisEngine:
    """Run a configurable list of analyzers and return an :class:`AnalysisResult`.

    Parameters
    ----------
    analyzers:
        Analyzers to run.  Defaults to :data:`DEFAULT_ANALYZERS`.
        Pass an explicit list to customise which checks run (useful for testing).
    """

    def __init__(self, analyzers: list[Analyzer] | None = None) -> None:
        self._analyzers: list[Analyzer] = (
            analyzers if analyzers is not None else list(DEFAULT_ANALYZERS)
        )

    @property
    def analyzer_names(self) -> list[str]:
        return [a.name for a in self._analyzers]  # type: ignore[attr-defined]

    def run(
        self,
        scan_result: ScanResult,
        project_result: ProjectDetectionResult,
    ) -> AnalysisResult:
        """Run all analyzers against the provided scan outputs.

        Each analyzer's exceptions are caught individually so one broken
        analyzer does not abort the whole run.
        """
        analysis = AnalysisResult(root=scan_result.root)

        for analyzer in self._analyzers:
            try:
                analyzer.analyze(scan_result, project_result, analysis)
            except Exception as exc:  # noqa: BLE001
                name = getattr(analyzer, "name", type(analyzer).__name__)
                analysis.errors.append(
                    f"{name} raised an unexpected error: {type(exc).__name__}: {exc}"
                )

        analysis.sort_issues()
        return analysis
