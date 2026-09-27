"""Data models for the AI analysis subsystem.

DiagnosticContext  — structured input given to an AI provider.
AIExplanation      — structured output returned by an AI provider.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Input: DiagnosticContext
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class CodeSnippet:
    """A relevant excerpt of source code with location metadata."""

    file: Path
    start_line: int
    end_line: int
    content: str
    language: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "file": str(self.file),
            "start_line": self.start_line,
            "end_line": self.end_line,
            "language": self.language,
            "content": self.content,
        }


@dataclasses.dataclass
class SyntaxErrorInfo:
    """A syntax error detected in a source file."""

    file: Path
    line: int | None
    message: str
    language: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "file": str(self.file),
            "line": self.line,
            "language": self.language,
            "message": self.message,
        }


@dataclasses.dataclass
class DependencyEdge:
    """A directed dependency relationship between two components."""

    source: str  # e.g. module or file name
    target: str
    kind: str = "imports"  # e.g. "imports", "requires", "extends"

    def as_dict(self) -> dict[str, Any]:
        return {"source": self.source, "target": self.target, "kind": self.kind}


@dataclasses.dataclass
class IssueInfo:
    """Lightweight summary of an analysis issue to include in a context."""

    issue_id: str
    title: str
    severity: str
    category: str
    description: str
    file: Path | None = None
    line: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "title": self.title,
            "severity": self.severity,
            "category": self.category,
            "description": self.description,
            "file": str(self.file) if self.file else None,
            "line": self.line,
        }


@dataclasses.dataclass
class DiagnosticContext:
    """All information an AI provider needs to explain a repository problem.

    Fields are optional so callers can include only what is relevant —
    avoid sending the whole repository.
    """

    # Repository-level metadata
    repo_root: Path
    project_types: list[str] = dataclasses.field(default_factory=list)
    ecosystems: list[str] = dataclasses.field(default_factory=list)

    # Relevant source files (paths only, no content)
    relevant_files: list[Path] = dataclasses.field(default_factory=list)

    # Source code snippets (with content)
    snippets: list[CodeSnippet] = dataclasses.field(default_factory=list)

    # Syntax errors detected by the static analyzer
    syntax_errors: list[SyntaxErrorInfo] = dataclasses.field(default_factory=list)

    # Dependency edges relevant to the problem
    dependency_edges: list[DependencyEdge] = dataclasses.field(default_factory=list)

    # Issues identified by the analysis engine
    issues: list[IssueInfo] = dataclasses.field(default_factory=list)

    # Free-form note that the caller can use to focus the AI's attention
    focus_note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "repo_root": str(self.repo_root),
            "project_types": self.project_types,
            "ecosystems": self.ecosystems,
            "relevant_files": [str(p) for p in self.relevant_files],
            "snippets": [s.as_dict() for s in self.snippets],
            "syntax_errors": [e.as_dict() for e in self.syntax_errors],
            "dependency_edges": [d.as_dict() for d in self.dependency_edges],
            "issues": [i.as_dict() for i in self.issues],
            "focus_note": self.focus_note,
        }


# ---------------------------------------------------------------------------
# Output: AIExplanation
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class AIExplanation:
    """Structured explanation produced by an AI provider.

    Parameters
    ----------
    root_cause:
        One-sentence statement of the most likely root cause.
    explanation:
        Detailed explanation of why the problem exists.
    recommended_fix:
        Concrete, actionable suggestion for resolving the problem.
    affected_components:
        Files or modules believed to be involved.
    confidence:
        Estimated confidence level: "high", "medium", or "low".
    provider:
        Name of the AI provider that produced this explanation.
    """

    root_cause: str
    explanation: str
    recommended_fix: str
    affected_components: list[str] = dataclasses.field(default_factory=list)
    confidence: str = "medium"  # "high" | "medium" | "low"
    provider: str = "unknown"

    def as_dict(self) -> dict[str, Any]:
        return {
            "root_cause": self.root_cause,
            "explanation": self.explanation,
            "recommended_fix": self.recommended_fix,
            "affected_components": self.affected_components,
            "confidence": self.confidence,
            "provider": self.provider,
        }
