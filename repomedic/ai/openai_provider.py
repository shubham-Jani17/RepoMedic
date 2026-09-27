"""OpenAIProvider — AI provider backed by the OpenAI Chat Completions API.

This module is an *optional* provider.  It is only active when:
  1. The ``openai`` Python package is installed.
  2. The ``REPOMEDIC_OPENAI_API_KEY`` environment variable is set
     (or the standard ``OPENAI_API_KEY`` variable is set as a fallback).

API keys are **never** hard-coded here.  They are read exclusively from
environment variables at runtime.

Configuration environment variables
------------------------------------
REPOMEDIC_OPENAI_API_KEY
    Primary key.  Takes precedence over ``OPENAI_API_KEY``.
OPENAI_API_KEY
    Fallback; used if the primary variable is absent.
REPOMEDIC_OPENAI_MODEL
    Model to use.  Defaults to ``gpt-4o-mini``.
REPOMEDIC_OPENAI_MAX_TOKENS
    Maximum tokens for the completion.  Defaults to 1024.
"""

from __future__ import annotations

import json
import os
from typing import Any

from repomedic.ai.base import AIAnalyzer, AIProviderError
from repomedic.ai.models import AIExplanation, DiagnosticContext

_DEFAULT_MODEL = "gpt-4o-mini"
_DEFAULT_MAX_TOKENS = 1024

_SYSTEM_PROMPT = """\
You are RepoMedic, an expert software-engineering assistant specialised in \
diagnosing repository health problems.

You will receive a structured JSON object describing a repository's issues, \
syntax errors, relevant source snippets, and dependency relationships.

Respond ONLY with a valid JSON object matching this schema (no markdown fences):
{
  "root_cause": "<one-sentence root cause>",
  "explanation": "<detailed explanation, 2-5 sentences>",
  "recommended_fix": "<concrete, actionable fix>",
  "affected_components": ["<file or module>", ...],
  "confidence": "<high|medium|low>"
}
"""


class OpenAIProvider(AIAnalyzer):
    """AI provider backed by the OpenAI Chat Completions API.

    Instantiation succeeds even if the ``openai`` package is absent or no
    API key is set — :meth:`is_available` will return ``False`` in those
    cases.  The :class:`~repomedic.ai.registry` factory uses
    :meth:`is_available` before selecting this provider.
    """

    name: str = "openai"

    def __init__(self) -> None:
        self._api_key: str = (
            os.environ.get("REPOMEDIC_OPENAI_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or ""
        )
        self._model: str = os.environ.get("REPOMEDIC_OPENAI_MODEL", _DEFAULT_MODEL)
        self._max_tokens: int = int(
            os.environ.get("REPOMEDIC_OPENAI_MAX_TOKENS", _DEFAULT_MAX_TOKENS)
        )

    def is_available(self) -> bool:
        """Return True only when both the openai package and an API key are present."""
        if not self._api_key:
            return False
        try:
            import openai  # noqa: F401
            return True
        except ImportError:
            return False

    def explain(self, context: DiagnosticContext) -> AIExplanation:
        """Call the OpenAI API and parse the structured response."""
        if not self._api_key:
            raise AIProviderError(
                "OpenAI API key not configured. "
                "Set REPOMEDIC_OPENAI_API_KEY or OPENAI_API_KEY."
            )

        try:
            import openai
        except ImportError as exc:
            raise AIProviderError(
                "The 'openai' package is not installed. "
                "Install it with: pip install openai"
            ) from exc

        client = openai.OpenAI(api_key=self._api_key)

        user_message = json.dumps(context.as_dict(), indent=2)

        try:
            response = client.chat.completions.create(
                model=self._model,
                max_tokens=self._max_tokens,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            raise AIProviderError(f"OpenAI API call failed: {exc}") from exc

        raw = response.choices[0].message.content or ""
        return self._parse_response(raw)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(raw: str) -> AIExplanation:
        try:
            data: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AIProviderError(
                f"OpenAI returned invalid JSON: {exc}\nRaw response:\n{raw}"
            ) from exc

        return AIExplanation(
            root_cause=data.get("root_cause", ""),
            explanation=data.get("explanation", ""),
            recommended_fix=data.get("recommended_fix", ""),
            affected_components=data.get("affected_components", []),
            confidence=data.get("confidence", "medium"),
            provider="openai",
        )
