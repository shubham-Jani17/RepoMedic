"""ContextBuilder — assemble a DiagnosticContext from analysis outputs.

The builder collects *only* the information relevant to understanding a
specific repository problem.  It does not read the entire repository;
it reads only small, targeted code snippets when needed.
"""

from __future__ import annotations

from pathlib import Path

from repomedic.ai.models import (
    CodeSnippet,
    DependencyEdge,
    DiagnosticContext,
    IssueInfo,
    SyntaxErrorInfo,
)
from repomedic.analyzer.models import AnalysisResult, Category, Issue
from repomedic.scanner.models import ScanResult
from repomedic.scanner.project_detector import ProjectDetectionResult

# Maximum number of surrounding lines to capture on each side of an issue.
_CONTEXT_LINES = 10

# Maximum number of issues to include in one context (keeps payloads small).
_MAX_ISSUES = 20

# Maximum length of a single code snippet (characters).
_MAX_SNIPPET_CHARS = 4_000


class ContextBuilder:
    """Build a :class:`~repomedic.ai.models.DiagnosticContext` from scan and
    analysis outputs.

    Usage::

        builder = ContextBuilder(scan_result, project_result, analysis_result)
        context = builder.build()

    Optional refinements
    --------------------
    *focus_issue_id* — restrict context to a single :class:`Issue` by its
    ``issue_id``.  When supplied, only that issue and its surrounding code
    are included.

    *focus_note* — free-form text appended to the context so the AI provider
    can orient its analysis toward a specific concern.
    """

    def __init__(
        self,
        scan_result: ScanResult,
        project_result: ProjectDetectionResult,
        analysis_result: AnalysisResult,
        *,
        focus_issue_id: str | None = None,
        focus_note: str = "",
    ) -> None:
        self._scan = scan_result
        self._project = project_result
        self._analysis = analysis_result
        self._focus_id = focus_issue_id
        self._focus_note = focus_note

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self) -> DiagnosticContext:
        """Return a populated :class:`DiagnosticContext`."""
        ctx = DiagnosticContext(
            repo_root=self._scan.root,
            project_types=list(self._project.project_types),
            ecosystems=list(self._project.ecosystems),
            focus_note=self._focus_note,
        )

        issues = self._select_issues()
        ctx.issues = [self._to_issue_info(i) for i in issues]

        # Collect syntax errors (always include them — they are the most
        # actionable piece of information available without an AI).
        ctx.syntax_errors = self._collect_syntax_errors(issues)

        # Collect relevant file paths (deduplicated, repo-relative).
        ctx.relevant_files = self._collect_relevant_files(issues)

        # Collect code snippets around each issue location.
        ctx.snippets = self._collect_snippets(issues)

        # Collect dependency edges for files involved in issues.
        ctx.dependency_edges = self._collect_dependency_edges(ctx.relevant_files)

        return ctx

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _select_issues(self) -> list[Issue]:
        """Return the issues to include in the context."""
        if self._focus_id:
            matching = [
                i for i in self._analysis.issues if i.issue_id == self._focus_id
            ]
            if matching:
                return matching
            # Fall through to full list if ID not found.

        # Take the highest-severity issues up to the cap.
        return self._analysis.issues[:_MAX_ISSUES]

    @staticmethod
    def _to_issue_info(issue: Issue) -> IssueInfo:
        return IssueInfo(
            issue_id=issue.issue_id,
            title=issue.title,
            severity=issue.severity.value,
            category=issue.category.value,
            description=issue.description,
            file=issue.file,
            line=issue.line,
        )

    @staticmethod
    def _collect_syntax_errors(issues: list[Issue]) -> list[SyntaxErrorInfo]:
        errors: list[SyntaxErrorInfo] = []
        for issue in issues:
            if issue.category == Category.SYNTAX and issue.file:
                errors.append(
                    SyntaxErrorInfo(
                        file=issue.file,
                        line=issue.line,
                        message=issue.description,
                    )
                )
        return errors

    def _collect_relevant_files(self, issues: list[Issue]) -> list[Path]:
        """Deduplicated list of repo-relative paths implicated by *issues*."""
        seen: set[Path] = set()
        result: list[Path] = []
        for issue in issues:
            if issue.file and issue.file not in seen:
                seen.add(issue.file)
                result.append(issue.file)
        return result

    def _collect_snippets(self, issues: list[Issue]) -> list[CodeSnippet]:
        """Read small source excerpts around each issue location."""
        snippets: list[CodeSnippet] = []
        # Track (file, start, end) to avoid duplicates when multiple issues
        # point to adjacent lines in the same file.
        seen: set[tuple[Path, int, int]] = set()

        for issue in issues:
            if not issue.file or not issue.line:
                continue

            absolute = self._scan.root / issue.file
            if not absolute.is_file():
                continue

            try:
                lines = absolute.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue

            total = len(lines)
            start = max(0, issue.line - 1 - _CONTEXT_LINES)
            end = min(total, issue.line - 1 + _CONTEXT_LINES + 1)

            key = (issue.file, start, end)
            if key in seen:
                continue
            seen.add(key)

            content = "\n".join(lines[start:end])
            if len(content) > _MAX_SNIPPET_CHARS:
                content = content[:_MAX_SNIPPET_CHARS] + "\n… (truncated)"

            language = _extension_to_language(issue.file.suffix)
            snippets.append(
                CodeSnippet(
                    file=issue.file,
                    start_line=start + 1,
                    end_line=end,
                    content=content,
                    language=language,
                )
            )

        return snippets

    def _collect_dependency_edges(self, relevant_files: list[Path]) -> list[DependencyEdge]:
        """Best-effort: extract import statements from relevant Python files.

        This keeps the context builder self-contained without depending on
        the optional graph subsystem.
        """
        edges: list[DependencyEdge] = []
        for rel_path in relevant_files:
            if rel_path.suffix != ".py":
                continue
            absolute = self._scan.root / rel_path
            if not absolute.is_file():
                continue
            try:
                source = absolute.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            module_name = str(rel_path).replace("\\", "/").replace("/", ".").removesuffix(".py")
            for line in source.splitlines():
                stripped = line.strip()
                target = _parse_import_target(stripped)
                if target:
                    edges.append(
                        DependencyEdge(
                            source=module_name,
                            target=target,
                            kind="imports",
                        )
                    )

        return edges


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _extension_to_language(suffix: str) -> str:
    _MAP = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".jsx": "javascript",
        ".tsx": "typescript",
        ".java": "java",
        ".kt": "kotlin",
        ".go": "go",
        ".rs": "rust",
        ".rb": "ruby",
        ".php": "php",
        ".cs": "csharp",
        ".cpp": "cpp",
        ".c": "c",
        ".sh": "bash",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".json": "json",
    }
    return _MAP.get(suffix.lower(), "")


def _parse_import_target(line: str) -> str | None:
    """Extract the top-level module name from a Python import statement."""
    if line.startswith("import "):
        # "import foo.bar as baz" → "foo.bar"
        rest = line[7:].split(" as ")[0].strip()
        # Take only the first module in a comma-separated list
        return rest.split(",")[0].strip() or None
    if line.startswith("from "):
        # "from foo.bar import baz" → "foo.bar"
        rest = line[5:].split(" import ")[0].strip()
        return rest or None
    return None
