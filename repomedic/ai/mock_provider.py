"""MockAIProvider — deterministic, offline AI provider for development and testing.

This provider inspects the :class:`~repomedic.ai.models.DiagnosticContext`
directly and synthesises a plausible explanation without making any network
calls.  It is always available and requires no configuration.

It is the default provider when no real AI backend is configured.
"""

from __future__ import annotations

from repomedic.ai.base import AIAnalyzer
from repomedic.ai.models import AIExplanation, DiagnosticContext


class MockAIProvider(AIAnalyzer):
    """Offline provider that generates rule-based explanations.

    The mock inspects the diagnostic context and returns a deterministic
    explanation derived from the issues, syntax errors, and dependency
    information already present.  It does not require any API key or
    network access.

    This provider is suitable for:
    - Development without AI credentials
    - Unit and integration tests
    - CI environments where external API calls are undesirable
    """

    name: str = "mock"

    def explain(self, context: DiagnosticContext) -> AIExplanation:  # noqa: D102
        root_cause = self._infer_root_cause(context)
        explanation = self._build_explanation(context)
        fix = self._build_fix(context)
        affected = self._affected_components(context)
        confidence = self._estimate_confidence(context)

        return AIExplanation(
            root_cause=root_cause,
            explanation=explanation,
            recommended_fix=fix,
            affected_components=affected,
            confidence=confidence,
            provider=self.name,
        )

    # ------------------------------------------------------------------
    # Internal synthesis helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_root_cause(ctx: DiagnosticContext) -> str:
        if ctx.syntax_errors:
            err = ctx.syntax_errors[0]
            loc = f" at {err.file}:{err.line}" if err.line else f" in {err.file}"
            return f"Syntax error{loc}: {err.message}"

        if ctx.issues:
            top = ctx.issues[0]
            loc = f" in {top.file}" if top.file else ""
            return f"{top.title}{loc} (severity: {top.severity})"

        return "No specific root cause identified from the available analysis data."

    @staticmethod
    def _build_explanation(ctx: DiagnosticContext) -> str:
        parts: list[str] = []

        if ctx.project_types:
            parts.append(
                f"This is a {', '.join(ctx.project_types)} project"
                + (f" ({', '.join(ctx.ecosystems)} ecosystem)" if ctx.ecosystems else "")
                + "."
            )

        if ctx.syntax_errors:
            for err in ctx.syntax_errors[:3]:
                line_info = f" on line {err.line}" if err.line else ""
                parts.append(
                    f"A syntax error was detected in {err.file}{line_info}: {err.message}"
                )
            if len(ctx.syntax_errors) > 3:
                parts.append(
                    f"… and {len(ctx.syntax_errors) - 3} more syntax error(s)."
                )
        elif ctx.issues:
            parts.append(
                f"The analysis found {len(ctx.issues)} issue(s). "
                f"The most severe is: {ctx.issues[0].title} — {ctx.issues[0].description}"
            )

        if ctx.dependency_edges:
            unique_sources = {e.source for e in ctx.dependency_edges}
            parts.append(
                f"{len(unique_sources)} file(s) have recorded import relationships "
                f"that may be affected."
            )

        if ctx.focus_note:
            parts.append(f"Additional context: {ctx.focus_note}")

        if not parts:
            parts.append(
                "No issues were detected in the provided context. "
                "The repository appears healthy."
            )

        return " ".join(parts)

    @staticmethod
    def _build_fix(ctx: DiagnosticContext) -> str:
        if ctx.syntax_errors:
            files = ", ".join(str(e.file) for e in ctx.syntax_errors[:3])
            return (
                f"Fix the syntax error(s) in: {files}. "
                "Run `python -m py_compile <file>` to verify each file parses correctly."
            )

        if not ctx.issues:
            return "No fixes required — no issues were found."

        top = ctx.issues[0]
        category = top.category

        recommendations: dict[str, str] = {
            "dependency": (
                "Review the dependency manifest and ensure a lock file is present "
                "and committed to the repository."
            ),
            "governance": (
                "Add the missing governance files (README, LICENSE, .gitignore) "
                "to improve repository health."
            ),
            "security": (
                "Address the security issue immediately. Review the affected code "
                "and apply the recommended remediation."
            ),
            "error": (
                "Investigate the reported error. Check logs, tracebacks, and "
                "any related configuration files."
            ),
        }

        return recommendations.get(
            category,
            f"Address the '{top.title}' issue. {top.description}",
        )

    @staticmethod
    def _affected_components(ctx: DiagnosticContext) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []

        for err in ctx.syntax_errors:
            key = str(err.file)
            if key not in seen:
                seen.add(key)
                result.append(key)

        for issue in ctx.issues:
            if issue.file:
                key = str(issue.file)
                if key not in seen:
                    seen.add(key)
                    result.append(key)

        return result

    @staticmethod
    def _estimate_confidence(ctx: DiagnosticContext) -> str:
        if ctx.syntax_errors:
            # Syntax errors are deterministic — we are very confident.
            return "high"
        if ctx.snippets:
            # We have actual code — medium confidence.
            return "medium"
        if ctx.issues:
            return "medium"
        return "low"
