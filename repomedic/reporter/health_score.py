"""HealthScoreCalculator — deterministic repository health score (0–100).

Scoring rules
=============

The score starts at **100** and deductions are applied for each issue found.
The final score is clamped to the range [0, 100].

Issue deductions
----------------
Each analysis issue reduces the score by an amount that depends on its
severity:

==========  ==========
Severity    Deduction
==========  ==========
CRITICAL    20 points
HIGH        10 points
MEDIUM       5 points
LOW          2 points
INFO         1 point
==========  ==========

Analyzer error penalty
----------------------
Each *internal* analyzer error (i.e. an analyzer that crashed, not a code
issue) deducts **5 points** from the score.  These represent gaps in
coverage — if an analyzer could not run, the repository's health cannot
be fully assessed.

Score ranges and status labels
-------------------------------
==========  =========  ===========
Score       Status     Meaning
==========  =========  ===========
90 – 100    healthy    Repository is in good shape.
60 –  89    warning    Some issues need attention.
 0 –  59    error      Significant problems detected.
==========  =========  ===========

Determinism guarantee
---------------------
Given the same set of issues and analyzer errors the score is always
identical regardless of the order in which results are evaluated.
"""

from __future__ import annotations

from repomedic.analyzer.models import AnalysisResult, Severity

# Points deducted per issue, keyed by severity.
DEDUCTIONS: dict[Severity, int] = {
    Severity.CRITICAL: 20,
    Severity.HIGH: 10,
    Severity.MEDIUM: 5,
    Severity.LOW: 2,
    Severity.INFO: 1,
}

# Points deducted per internal analyzer error.
ANALYZER_ERROR_PENALTY: int = 5

# Score thresholds for status labels.
_HEALTHY_THRESHOLD = 90
_WARNING_THRESHOLD = 60


class HealthScoreCalculator:
    """Compute a deterministic health score from an :class:`AnalysisResult`.

    Usage::

        calc = HealthScoreCalculator()
        score = calc.score(analysis)
        label = calc.status(score)

    Both :meth:`score` and :meth:`status` are pure functions with no
    side-effects.
    """

    def score(self, analysis: AnalysisResult) -> int:
        """Return an integer score in the range [0, 100].

        Parameters
        ----------
        analysis:
            Output of :class:`~repomedic.analyzer.engine.AnalysisEngine`.
        """
        total = 100

        for issue in analysis.issues:
            total -= DEDUCTIONS.get(issue.severity, 0)

        total -= len(analysis.errors) * ANALYZER_ERROR_PENALTY

        return max(0, min(100, total))

    @staticmethod
    def status(score: int) -> str:
        """Return the status label for a given score.

        Parameters
        ----------
        score:
            An integer in [0, 100] as returned by :meth:`score`.

        Returns
        -------
        str
            ``"healthy"``, ``"warning"``, or ``"error"``.
        """
        if score >= _HEALTHY_THRESHOLD:
            return "healthy"
        if score >= _WARNING_THRESHOLD:
            return "warning"
        return "error"
