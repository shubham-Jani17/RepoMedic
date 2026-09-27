"""PatchGenerator — produce FixSuggestion objects from an AnalysisResult.

The PatchGenerator translates analysis issues into proposed fixes.
It performs **no filesystem operations** — it only reads the analysis
output and returns :class:`~repomedic.fixer.models.FixSuggestion` objects.

Only governance issues (missing .gitignore, README.md, LICENSE) are
supported today.  Issues from other categories are noted in
:attr:`PatchGenerator.unsupported` so callers can inform the user.
"""

from __future__ import annotations

import datetime
from pathlib import Path

from repomedic.analyzer.models import AnalysisResult, Category, Issue
from repomedic.fixer import templates
from repomedic.fixer.models import FixKind, FixSuggestion

# Map of issue title prefix → (target filename, template, rationale)
# Matched case-insensitively against Issue.title.
_GOVERNANCE_RULES: list[tuple[str, str, str, str]] = [
    (
        "Missing .gitignore",
        ".gitignore",
        "GITIGNORE",
        "A .gitignore file prevents build artefacts and secrets from being "
        "accidentally committed.",
    ),
    (
        "Missing README",
        "README.md",
        "README_MD",
        "A README.md gives newcomers an overview of the project and how to "
        "get started.",
    ),
    (
        "Missing LICENSE",
        "LICENSE",
        "LICENSE_MIT",
        "A LICENSE file establishes the legal terms under which the code may "
        "be used, modified, and distributed.",
    ),
]


class PatchGenerator:
    """Translate analysis issues into :class:`~repomedic.fixer.models.FixSuggestion` objects.

    Parameters
    ----------
    project_name:
        Used to populate the ``{{PROJECT_NAME}}`` placeholder in the
        README template.  Defaults to the repository directory name.
    author:
        Used to populate the ``{{AUTHOR}}`` placeholder in the LICENSE
        template.  Defaults to an empty string.
    year:
        Used to populate the ``{{YEAR}}`` placeholder in the LICENSE
        template.  Defaults to the current calendar year.
    """

    def __init__(
        self,
        project_name: str = "",
        author: str = "",
        year: str = "",
    ) -> None:
        self._project_name = project_name
        self._author = author or "the project contributors"
        self._year = year or str(datetime.datetime.now(datetime.timezone.utc).year)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        analysis: AnalysisResult,
    ) -> tuple[list[FixSuggestion], list[Issue]]:
        """Return ``(suggestions, unsupported_issues)``.

        Parameters
        ----------
        analysis:
            Output of :class:`~repomedic.analyzer.engine.AnalysisEngine`.

        Returns
        -------
        suggestions:
            One :class:`FixSuggestion` per supported, fixable issue.
        unsupported:
            Issues for which no automated fix is available.
        """
        project_name = self._project_name or analysis.root.name

        suggestions: list[FixSuggestion] = []
        unsupported: list[Issue] = []

        for issue in analysis.issues:
            suggestion = self._try_generate(issue, project_name)
            if suggestion is not None:
                suggestions.append(suggestion)
            else:
                unsupported.append(issue)

        return suggestions, unsupported

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _try_generate(self, issue: Issue, project_name: str) -> FixSuggestion | None:
        """Return a FixSuggestion for *issue*, or None if unsupported."""
        if issue.category != Category.GOVERNANCE:
            return None

        for title_prefix, filename, template_attr, rationale in _GOVERNANCE_RULES:
            if issue.title.lower().startswith(title_prefix.lower()):
                content = self._render(template_attr, project_name)
                return FixSuggestion(
                    issue_id=issue.issue_id,
                    issue_title=issue.title,
                    kind=FixKind.CREATE_FILE,
                    target_path=Path(filename),
                    content=content,
                    rationale=rationale,
                )

        # Governance issue with no matching rule
        return None

    def _render(self, template_attr: str, project_name: str) -> str:
        raw: str = getattr(templates, template_attr)
        return templates.render(
            raw,
            PROJECT_NAME=project_name,
            AUTHOR=self._author,
            YEAR=self._year,
        )
