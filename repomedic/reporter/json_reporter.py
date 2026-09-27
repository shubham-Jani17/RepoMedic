"""JSONReporter — serialise a :class:`~repomedic.reporter.models.ReportData`
to valid, machine-readable JSON.

The output schema matches the documented contract::

    {
      "repository": "...",
      "status": "...",
      "health_score": 0,
      "total_issues": 0,
      "total_errors": 0,
      "total_warnings": 0,
      "project_types": [...],
      "languages": [...],
      "verification_status": "...",
      "governance_status": "...",
      "errors": [...],
      "warnings": [...],
      "issues": [
        {
          "id": "...",
          "title": "...",
          "severity": "...",
          "category": "...",
          "description": "...",
          "recommendation": "...",
          "file": "..." | null,
          "line": 0 | null
        },
        ...
      ]
    }
"""

from __future__ import annotations

import json
from typing import Any, TextIO
import sys

from repomedic.reporter.models import ReportData


class JSONReporter:
    """Serialise a :class:`~repomedic.reporter.models.ReportData` to JSON.

    Parameters
    ----------
    stream:
        Output stream.  Defaults to ``sys.stdout``.
    indent:
        JSON indentation level.  Defaults to 2.
    """

    def __init__(
        self,
        stream: TextIO | None = None,
        *,
        indent: int = 2,
    ) -> None:
        self._stream = stream or sys.stdout
        self._indent = indent

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def render(self, data: ReportData) -> None:
        """Write a JSON document to :attr:`_stream`."""
        payload = self.to_dict(data)
        json.dump(payload, self._stream, indent=self._indent)
        print(file=self._stream)  # trailing newline

    def to_dict(self, data: ReportData) -> dict[str, Any]:
        """Return the report as a plain Python dictionary.

        Issues are normalised to the documented schema with explicit
        ``"id"``, ``"file"``, and ``"line"`` keys (even when ``None``).
        """
        issues = [self._normalise_issue(i) for i in data.issues]
        base = data.as_dict()
        base["issues"] = issues
        return base

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_issue(raw: dict[str, Any]) -> dict[str, Any]:
        """Ensure a consistent shape for each issue entry."""
        return {
            "id": raw.get("issue_id") or raw.get("id") or "",
            "title": raw.get("title", ""),
            "severity": raw.get("severity", "info"),
            "category": raw.get("category", "other"),
            "description": raw.get("description", ""),
            "recommendation": raw.get("recommendation", ""),
            "file": raw.get("file"),
            "line": raw.get("line"),
        }
