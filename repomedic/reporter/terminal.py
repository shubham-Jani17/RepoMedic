"""TerminalReporter — render a :class:`~repomedic.reporter.models.ReportData`
to a human-readable terminal report.

Produces no colour codes when stdout is not a TTY (e.g. when piped to a
file or another process).
"""

from __future__ import annotations

import sys
from typing import TextIO

from repomedic.reporter.models import ReportData

# ---------------------------------------------------------------------------
# ANSI helpers (duplicated locally so the reporter has no CLI dependency)
# ---------------------------------------------------------------------------

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_CYAN = "\033[36m"
_MAGENTA = "\033[35m"
_BLUE = "\033[34m"

# Severity → ANSI colour code
_SEVERITY_COLOUR: dict[str, str] = {
    "critical": _MAGENTA,
    "high": _RED,
    "medium": _YELLOW,
    "low": _BLUE,
    "info": _CYAN,
}

# Status → ANSI colour code
_STATUS_COLOUR: dict[str, str] = {
    "healthy": _GREEN,
    "warning": _YELLOW,
    "error": _RED,
}

# Score gauge characters — ASCII fallbacks to avoid UnicodeEncodeError on Windows
# (cp1252 cannot encode U+2588 or U+2591)
_GAUGE_FILL = "#"
_GAUGE_EMPTY = "-"
_GAUGE_WIDTH = 30


def _c(text: str, *codes: str, stream: TextIO = sys.stdout) -> str:
    """Apply ANSI codes only when *stream* is a real terminal."""
    if stream.isatty():
        return "".join(codes) + text + _RESET
    return text


class TerminalReporter:
    """Render a :class:`~repomedic.reporter.models.ReportData` to a text stream.

    Parameters
    ----------
    stream:
        Output stream.  Defaults to ``sys.stdout``.
    show_all_issues:
        When ``True``, print every individual issue.
        When ``False`` (default), only issues with severity ≥ MEDIUM are shown
        in the issue list section.
    """

    def __init__(
        self,
        stream: TextIO | None = None,
        *,
        show_all_issues: bool = False,
    ) -> None:
        self._stream = stream or sys.stdout
        self._show_all = show_all_issues

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def render(self, data: ReportData) -> None:
        """Write the full report to :attr:`_stream`."""
        w = self._w
        st = self._stream

        w()
        w(_c("Repository Health Report", _BOLD, stream=st))
        w(_c("-" * 42, _DIM, stream=st))
        w()

        # --- Repository metadata ---
        w(_c("  Repository   : ", _DIM, stream=st) + _c(str(data.repo_root), _CYAN, stream=st))

        if data.project_types:
            w(_c("  Project type : ", _DIM, stream=st) + ", ".join(data.project_types))
        if data.languages:
            w(_c("  Languages    : ", _DIM, stream=st) + ", ".join(data.languages))
        w()

        # --- Health score + gauge ---
        score = data.health_score
        status_colour = _STATUS_COLOUR.get(data.status, "")
        filled = round(_GAUGE_WIDTH * score / 100)
        gauge = (
            _c(_GAUGE_FILL * filled, status_colour, stream=st)
            + _c(_GAUGE_EMPTY * (_GAUGE_WIDTH - filled), _DIM, stream=st)
        )
        w(
            _c("  Health score : ", _DIM, stream=st)
            + _c(f"{score:>3}/100", status_colour, _BOLD, stream=st)
            + f"  [{gauge}]"
            + "  "
            + _c(data.status.upper(), status_colour, _BOLD, stream=st)
        )
        w()

        # --- Counts ---
        issue_colour = _GREEN if data.total_issues == 0 else _RED
        w(
            _c("  Total issues : ", _DIM, stream=st)
            + _c(str(data.total_issues), issue_colour, stream=st)
        )

        if data.total_errors:
            w(
                _c("  Errors       : ", _DIM, stream=st)
                + _c(str(data.total_errors), _RED, stream=st)
            )
        if data.total_warnings:
            w(
                _c("  Warnings     : ", _DIM, stream=st)
                + _c(str(data.total_warnings), _YELLOW, stream=st)
            )
        w()

        # --- Verification status ---
        vstatus = data.verification_status
        vstatus_colour = _GREEN if vstatus == "passed" else (_RED if vstatus == "failed" else _DIM)
        w(
            _c("  Verification : ", _DIM, stream=st)
            + _c(vstatus.upper(), vstatus_colour, stream=st)
        )

        # --- Governance status ---
        gstatus = data.governance_status
        gcolour = _GREEN if gstatus == "ok" else _YELLOW
        w(
            _c("  Governance   : ", _DIM, stream=st)
            + _c(gstatus.upper(), gcolour, stream=st)
        )
        w()

        # --- Severity breakdown ---
        sev_counts = self._severity_counts(data)
        if any(sev_counts.values()):
            w(_c("  Severity breakdown:", _BOLD, stream=st))
            for sev, count in sev_counts.items():
                if count:
                    col = _SEVERITY_COLOUR.get(sev, "")
                    bar = _c("#" * min(count, 20), col, stream=st)
                    w(f"    {sev.upper():<10} {count:>4}  {bar}")
            w()

        # --- Issue list ---
        visible = [
            i for i in data.issues
            if self._show_all or i.get("severity", "") in ("critical", "high", "medium")
        ]
        if visible:
            w(_c(f"  Issues ({len(visible)} shown):", _BOLD, stream=st))
            w()
            for issue in visible:
                sev = issue.get("severity", "info")
                col = _SEVERITY_COLOUR.get(sev, "")
                sev_label = _c(f"[{sev.upper():<8}]", col, stream=st)
                title = _c(issue.get("title", ""), _BOLD, stream=st)

                loc = ""
                if issue.get("file"):
                    loc = f"  {_c(issue['file'], _DIM, stream=st)}"
                    if issue.get("line"):
                        loc += f":{issue['line']}"

                w(f"  {sev_label} {title}{loc}")
                desc = issue.get("description", "")
                if desc:
                    w(f"  {'':12}  {desc[:140]}")
                rec = issue.get("recommendation", "")
                if rec:
                    w(f"  {'':12}  {_c('Fix:', _DIM, stream=st)} {rec[:120]}")
                w()

        # --- Errors ---
        if data.errors:
            w(_c(f"  Analyzer errors ({len(data.errors)}):", _RED, stream=st))
            for err in data.errors:
                w(f"    {err}")
            w()

        # --- Warnings ---
        if data.warnings:
            w(_c(f"  Warnings ({len(data.warnings)}):", _DIM, stream=st))
            for warn in data.warnings:
                w(f"    {warn}")
            w()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _w(self, text: str = "") -> None:
        """Write a line to the stream."""
        print(text, file=self._stream)

    @staticmethod
    def _severity_counts(data: ReportData) -> dict[str, int]:
        counts: dict[str, int] = {
            "critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0
        }
        for issue in data.issues:
            sev = issue.get("severity", "info")
            if sev in counts:
                counts[sev] += 1
        return counts
