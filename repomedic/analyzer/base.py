"""Base Analyzer protocol — all analyzers implement this interface."""

from __future__ import annotations

from typing import Protocol

from repomedic.analyzer.models import AnalysisResult
from repomedic.scanner.models import ScanResult
from repomedic.scanner.project_detector import ProjectDetectionResult


class Analyzer(Protocol):
    """Protocol every concrete analyzer must satisfy.

    An analyzer receives the outputs from the scanner phase and appends
    :class:`~repomedic.analyzer.models.Issue` objects to *result*.  It may
    also record internal errors via ``result.errors``.

    Analyzers must **not** perform their own filesystem scans — they should
    work exclusively from the provided *scan_result* and *project_result*.
    The exception is :class:`~repomedic.analyzer.syntax.SyntaxAnalyzer` which
    must read file content, but only for files already enumerated by the scanner.
    """

    @property
    def name(self) -> str:
        """Human-readable name shown in the CLI."""
        ...

    def analyze(
        self,
        scan_result: ScanResult,
        project_result: ProjectDetectionResult,
        result: AnalysisResult,
    ) -> None:
        """Run analysis and append findings to *result*."""
        ...
