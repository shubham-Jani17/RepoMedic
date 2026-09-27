"""Reporting subsystem — health score, terminal and JSON reports.

Public API
----------
ReportData           — intermediate model carrying all report fields
HealthScoreCalculator — deterministic 0–100 score from analysis results
DEDUCTIONS           — per-severity point deductions (documented constant)
ReportBuilder        — assemble a ReportData from pipeline outputs
TerminalReporter     — human-readable terminal output
JSONReporter         — machine-readable JSON output
"""

from repomedic.reporter.builder import ReportBuilder
from repomedic.reporter.health_score import DEDUCTIONS, HealthScoreCalculator
from repomedic.reporter.json_reporter import JSONReporter
from repomedic.reporter.models import ReportData
from repomedic.reporter.terminal import TerminalReporter

__all__ = [
    "DEDUCTIONS",
    "HealthScoreCalculator",
    "JSONReporter",
    "ReportBuilder",
    "ReportData",
    "TerminalReporter",
]
