"""Analyzer subsystem — problem identification and root-cause analysis."""

from repomedic.analyzer.dependency import DependencyAnalyzer
from repomedic.analyzer.engine import DEFAULT_ANALYZERS, AnalysisEngine
from repomedic.analyzer.error import ErrorAnalyzer
from repomedic.analyzer.governance import GovernanceAnalyzer
from repomedic.analyzer.models import (
    AnalysisResult,
    Category,
    Issue,
    Severity,
    SEVERITY_COLOURS,
    SEVERITY_LABELS,
)
from repomedic.analyzer.syntax import SyntaxAnalyzer

__all__ = [
    # engine
    "DEFAULT_ANALYZERS",
    "AnalysisEngine",
    # concrete analyzers
    "DependencyAnalyzer",
    "ErrorAnalyzer",
    "GovernanceAnalyzer",
    "SyntaxAnalyzer",
    # models
    "AnalysisResult",
    "Category",
    "Issue",
    "Severity",
    "SEVERITY_COLOURS",
    "SEVERITY_LABELS",
]
