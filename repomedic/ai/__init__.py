"""AI analysis subsystem — provider-independent explanation engine.

Public API
----------
DiagnosticContext   — structured input built by ContextBuilder
AIExplanation       — structured output returned by an AI provider
CodeSnippet         — source code excerpt with location metadata
SyntaxErrorInfo     — syntax error detected in a source file
DependencyEdge      — directed dependency relationship
IssueInfo           — lightweight issue summary for context

AIAnalyzer          — abstract provider interface
AIProviderError     — raised on provider failure
MockAIProvider      — offline, deterministic provider (dev / CI)
OpenAIProvider      — OpenAI Chat Completions backend (optional)

ContextBuilder      — builds a DiagnosticContext from scan + analysis output
get_analyzer        — factory: select and return the configured provider
ProviderNotAvailableError — raised when the requested provider is unavailable
"""

from repomedic.ai.base import AIAnalyzer, AIProviderError
from repomedic.ai.context_builder import ContextBuilder
from repomedic.ai.mock_provider import MockAIProvider
from repomedic.ai.models import (
    AIExplanation,
    CodeSnippet,
    DependencyEdge,
    DiagnosticContext,
    IssueInfo,
    SyntaxErrorInfo,
)
from repomedic.ai.openai_provider import OpenAIProvider
from repomedic.ai.registry import ProviderNotAvailableError, get_analyzer

__all__ = [
    # models
    "AIExplanation",
    "CodeSnippet",
    "DependencyEdge",
    "DiagnosticContext",
    "IssueInfo",
    "SyntaxErrorInfo",
    # base
    "AIAnalyzer",
    "AIProviderError",
    # providers
    "MockAIProvider",
    "OpenAIProvider",
    # builder
    "ContextBuilder",
    # registry
    "get_analyzer",
    "ProviderNotAvailableError",
]
