"""AI provider registry — select and instantiate the configured AI provider.

Usage
-----
::

    from repomedic.ai.registry import get_analyzer

    analyzer = get_analyzer()          # auto-selects based on environment
    explanation = analyzer.explain(context)

Provider selection
------------------
The provider is chosen by reading the ``REPOMEDIC_AI_PROVIDER`` environment
variable (case-insensitive).  When the variable is absent, the registry tries
each built-in provider in priority order and returns the first one that is
available.

Supported values for ``REPOMEDIC_AI_PROVIDER``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``openai``
    Use :class:`~repomedic.ai.openai_provider.OpenAIProvider`.
    Requires the ``openai`` package and a valid API key in
    ``REPOMEDIC_OPENAI_API_KEY`` or ``OPENAI_API_KEY``.

``mock``
    Use :class:`~repomedic.ai.mock_provider.MockAIProvider` (no network,
    no credentials required — always works).

If an explicitly requested provider is not available (e.g. missing package
or key), :func:`get_analyzer` raises :class:`ProviderNotAvailableError`
instead of silently falling back so that misconfiguration is surfaced early.
"""

from __future__ import annotations

import os

from repomedic.ai.base import AIAnalyzer
from repomedic.ai.mock_provider import MockAIProvider
from repomedic.ai.openai_provider import OpenAIProvider


class ProviderNotAvailableError(Exception):
    """Raised when the requested AI provider cannot be initialised."""


# Ordered list of providers tried during auto-selection.
# Earlier entries have higher priority.
_AUTO_CANDIDATES: list[type[AIAnalyzer]] = [
    OpenAIProvider,
    MockAIProvider,
]

_PROVIDER_MAP: dict[str, type[AIAnalyzer]] = {
    "openai": OpenAIProvider,
    "mock": MockAIProvider,
}


def get_analyzer(provider: str | None = None) -> AIAnalyzer:
    """Return a ready-to-use :class:`~repomedic.ai.base.AIAnalyzer`.

    Parameters
    ----------
    provider:
        Override the provider name.  When ``None``, the value of the
        ``REPOMEDIC_AI_PROVIDER`` environment variable is used, or
        auto-selection is performed if that variable is also absent.

    Returns
    -------
    AIAnalyzer
        An initialised, available provider instance.

    Raises
    ------
    ProviderNotAvailableError
        If the requested provider cannot be initialised.
    ValueError
        If the provider name is not recognised.
    """
    name = provider or os.environ.get("REPOMEDIC_AI_PROVIDER", "").strip().lower()

    if name:
        if name not in _PROVIDER_MAP:
            raise ValueError(
                f"Unknown AI provider: {name!r}. "
                f"Known providers: {sorted(_PROVIDER_MAP)}"
            )
        instance = _PROVIDER_MAP[name]()
        if not instance.is_available():
            raise ProviderNotAvailableError(
                f"Provider '{name}' is configured but not available. "
                "Check that all required packages are installed and "
                "environment variables are set."
            )
        return instance

    # Auto-select the first available provider.
    for cls in _AUTO_CANDIDATES:
        instance = cls()
        if instance.is_available():
            return instance

    # This should never happen because MockAIProvider is always available,
    # but be defensive.
    raise ProviderNotAvailableError(
        "No AI provider is available. This is an internal error."
    )
