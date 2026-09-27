"""Abstract base class for AI analysis providers.

All concrete providers must implement :class:`AIAnalyzer`.
The interface is kept deliberately thin so that any backend
(cloud LLM, local model, mock) can be plugged in without
touching the rest of RepoMedic.
"""

from __future__ import annotations

import abc

from repomedic.ai.models import AIExplanation, DiagnosticContext


class AIAnalyzer(abc.ABC):
    """Provider-independent interface for AI-powered diagnosis.

    Implement this class to integrate a new AI backend.  The only
    required method is :meth:`explain`.

    Parameters
    ----------
    name:
        Human-readable provider name, returned in every
        :class:`~repomedic.ai.models.AIExplanation` produced by this
        provider.
    """

    #: Short identifier for this provider, e.g. ``"openai"`` or ``"mock"``.
    name: str = "base"

    @abc.abstractmethod
    def explain(self, context: DiagnosticContext) -> AIExplanation:
        """Analyse *context* and return a structured explanation.

        Parameters
        ----------
        context:
            Structured diagnostic context built by
            :class:`~repomedic.ai.context_builder.ContextBuilder`.

        Returns
        -------
        AIExplanation
            Structured explanation of the most likely root cause.

        Raises
        ------
        AIProviderError
            If the provider cannot produce an explanation (e.g. network
            error, invalid API key, quota exceeded).
        """

    def is_available(self) -> bool:
        """Return *True* if this provider is properly configured.

        Concrete providers should override this to check that all required
        credentials or dependencies are present before attempting a call.
        The default implementation always returns ``True``.
        """
        return True


class AIProviderError(Exception):
    """Raised when an AI provider fails to produce an explanation."""
