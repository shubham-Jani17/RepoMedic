"""Tests for the AI analysis subsystem.

All tests use the MockAIProvider — no network calls, no API keys required.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from repomedic.ai.base import AIAnalyzer, AIProviderError
from repomedic.ai.context_builder import ContextBuilder, _parse_import_target
from repomedic.ai.mock_provider import MockAIProvider
from repomedic.ai.models import (
    AIExplanation,
    CodeSnippet,
    DependencyEdge,
    DiagnosticContext,
    IssueInfo,
    SyntaxErrorInfo,
)
from repomedic.ai.registry import ProviderNotAvailableError, get_analyzer
from repomedic.analyzer.models import AnalysisResult, Category, Issue, Severity
from repomedic.cli.main import cli
from repomedic.scanner.models import FileEntry, ScanResult
from repomedic.scanner.project_detector import ProjectDetectionResult


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_scan_result(root: Path, files: list[FileEntry] | None = None) -> ScanResult:
    return ScanResult(root=root, files=files or [])


def _make_issue(
    *,
    title: str = "Test issue",
    severity: Severity = Severity.MEDIUM,
    category: Category = Category.SYNTAX,
    file: Path | None = None,
    line: int | None = None,
    issue_id: str = "test0001",
) -> Issue:
    return Issue(
        issue_id=issue_id,
        title=title,
        severity=severity,
        category=category,
        description=f"Description of {title}",
        recommendation=f"Fix for {title}",
        file=file,
        line=line,
    )


# ---------------------------------------------------------------------------
# DiagnosticContext model tests
# ---------------------------------------------------------------------------


class TestDiagnosticContextModel:
    def test_as_dict_contains_expected_keys(self, tmp_path: Path) -> None:
        ctx = DiagnosticContext(
            repo_root=tmp_path,
            project_types=["Python"],
            ecosystems=["Python"],
        )
        d = ctx.as_dict()
        assert d["repo_root"] == str(tmp_path)
        assert d["project_types"] == ["Python"]
        assert d["ecosystems"] == ["Python"]
        assert d["issues"] == []
        assert d["snippets"] == []
        assert d["syntax_errors"] == []

    def test_code_snippet_as_dict(self, tmp_path: Path) -> None:
        snippet = CodeSnippet(
            file=Path("src/foo.py"),
            start_line=10,
            end_line=20,
            content="def foo(): pass",
            language="python",
        )
        d = snippet.as_dict()
        assert d["start_line"] == 10
        assert d["language"] == "python"
        assert "foo" in d["content"]

    def test_ai_explanation_as_dict(self) -> None:
        exp = AIExplanation(
            root_cause="Bad syntax",
            explanation="A syntax error was introduced.",
            recommended_fix="Fix the syntax error.",
            affected_components=["src/foo.py"],
            confidence="high",
            provider="mock",
        )
        d = exp.as_dict()
        assert d["root_cause"] == "Bad syntax"
        assert d["confidence"] == "high"
        assert d["provider"] == "mock"
        assert "src/foo.py" in d["affected_components"]


# ---------------------------------------------------------------------------
# ContextBuilder tests
# ---------------------------------------------------------------------------


class TestContextBuilder:
    def test_empty_analysis_produces_minimal_context(self, tmp_path: Path) -> None:
        scan = _make_scan_result(tmp_path)
        proj = ProjectDetectionResult()
        analysis = AnalysisResult(root=tmp_path)

        ctx = ContextBuilder(scan, proj, analysis).build()

        assert ctx.repo_root == tmp_path
        assert ctx.issues == []
        assert ctx.snippets == []
        assert ctx.syntax_errors == []

    def test_issues_are_included_in_context(self, tmp_path: Path) -> None:
        scan = _make_scan_result(tmp_path)
        proj = ProjectDetectionResult()
        analysis = AnalysisResult(root=tmp_path)
        analysis.issues.append(
            _make_issue(title="Missing lock file", category=Category.DEPENDENCY)
        )

        ctx = ContextBuilder(scan, proj, analysis).build()

        assert len(ctx.issues) == 1
        assert ctx.issues[0].title == "Missing lock file"

    def test_syntax_errors_are_extracted(self, tmp_path: Path) -> None:
        scan = _make_scan_result(tmp_path)
        proj = ProjectDetectionResult()
        analysis = AnalysisResult(root=tmp_path)
        analysis.issues.append(
            _make_issue(
                title="Python syntax error",
                category=Category.SYNTAX,
                file=Path("bad.py"),
                line=5,
            )
        )

        ctx = ContextBuilder(scan, proj, analysis).build()

        assert len(ctx.syntax_errors) == 1
        assert ctx.syntax_errors[0].line == 5
        assert str(ctx.syntax_errors[0].file) == "bad.py"

    def test_relevant_files_are_deduplicated(self, tmp_path: Path) -> None:
        scan = _make_scan_result(tmp_path)
        proj = ProjectDetectionResult()
        analysis = AnalysisResult(root=tmp_path)
        # Two issues in the same file
        for i in range(2):
            analysis.issues.append(
                _make_issue(file=Path("shared.py"), line=i + 1, issue_id=f"id{i:04d}")
            )

        ctx = ContextBuilder(scan, proj, analysis).build()

        assert ctx.relevant_files.count(Path("shared.py")) == 1

    def test_snippets_are_read_for_file_issues(self, tmp_path: Path) -> None:
        source_file = tmp_path / "example.py"
        source_file.write_text("x = 1\ny = 2\nz = 3\n", encoding="utf-8")

        entry = FileEntry(
            absolute_path=source_file,
            relative_path=Path("example.py"),
            filename="example.py",
            extension=".py",
            size_bytes=source_file.stat().st_size,
        )
        scan = _make_scan_result(tmp_path, files=[entry])
        proj = ProjectDetectionResult()
        analysis = AnalysisResult(root=tmp_path)
        analysis.issues.append(
            _make_issue(file=Path("example.py"), line=2, category=Category.SYNTAX)
        )

        ctx = ContextBuilder(scan, proj, analysis).build()

        assert len(ctx.snippets) == 1
        assert "y = 2" in ctx.snippets[0].content

    def test_dependency_edges_extracted_from_python(self, tmp_path: Path) -> None:
        source_file = tmp_path / "service.py"
        source_file.write_text(
            "import os\nfrom pathlib import Path\nimport json\n", encoding="utf-8"
        )
        entry = FileEntry(
            absolute_path=source_file,
            relative_path=Path("service.py"),
            filename="service.py",
            extension=".py",
            size_bytes=source_file.stat().st_size,
        )
        scan = _make_scan_result(tmp_path, files=[entry])
        proj = ProjectDetectionResult()
        analysis = AnalysisResult(root=tmp_path)
        analysis.issues.append(_make_issue(file=Path("service.py"), line=1))

        ctx = ContextBuilder(scan, proj, analysis).build()

        targets = {e.target for e in ctx.dependency_edges}
        assert "os" in targets
        assert "pathlib" in targets
        assert "json" in targets

    def test_focus_issue_id_restricts_issues(self, tmp_path: Path) -> None:
        scan = _make_scan_result(tmp_path)
        proj = ProjectDetectionResult()
        analysis = AnalysisResult(root=tmp_path)
        issue_a = _make_issue(title="Issue A", issue_id="aaaa0001")
        issue_b = _make_issue(title="Issue B", issue_id="bbbb0002")
        analysis.issues.extend([issue_a, issue_b])

        ctx = ContextBuilder(
            scan, proj, analysis, focus_issue_id="aaaa0001"
        ).build()

        assert len(ctx.issues) == 1
        assert ctx.issues[0].issue_id == "aaaa0001"

    def test_focus_issue_id_falls_back_to_all_issues_when_not_found(
        self, tmp_path: Path
    ) -> None:
        scan = _make_scan_result(tmp_path)
        proj = ProjectDetectionResult()
        analysis = AnalysisResult(root=tmp_path)
        analysis.issues.extend([
            _make_issue(title="Issue A", issue_id="aaaa0001"),
            _make_issue(title="Issue B", issue_id="bbbb0002"),
        ])

        ctx = ContextBuilder(
            scan, proj, analysis, focus_issue_id="nonexistent"
        ).build()

        assert len(ctx.issues) == 2

    def test_focus_note_is_propagated(self, tmp_path: Path) -> None:
        scan = _make_scan_result(tmp_path)
        proj = ProjectDetectionResult()
        analysis = AnalysisResult(root=tmp_path)

        ctx = ContextBuilder(
            scan, proj, analysis, focus_note="Pay attention to import cycles."
        ).build()

        assert ctx.focus_note == "Pay attention to import cycles."

    def test_project_types_from_detection_result(self, tmp_path: Path) -> None:
        from repomedic.scanner.project_detector import ConfigFileSpec, DetectedConfigFile

        spec = ConfigFileSpec(
            filename="pyproject.toml",
            project_type="Python",
            ecosystem="Python",
            description="PEP 517/518",
        )
        proj = ProjectDetectionResult(
            detected_configs=[
                DetectedConfigFile(spec=spec, relative_path=Path("pyproject.toml"))
            ]
        )
        scan = _make_scan_result(tmp_path)
        analysis = AnalysisResult(root=tmp_path)

        ctx = ContextBuilder(scan, proj, analysis).build()

        assert "Python" in ctx.project_types


# ---------------------------------------------------------------------------
# MockAIProvider tests
# ---------------------------------------------------------------------------


class TestMockAIProvider:
    def test_is_available_always_true(self) -> None:
        assert MockAIProvider().is_available() is True

    def test_explain_returns_ai_explanation(self, tmp_path: Path) -> None:
        ctx = DiagnosticContext(repo_root=tmp_path, project_types=["Python"])
        result = MockAIProvider().explain(ctx)
        assert isinstance(result, AIExplanation)
        assert result.provider == "mock"

    def test_syntax_error_root_cause(self, tmp_path: Path) -> None:
        ctx = DiagnosticContext(
            repo_root=tmp_path,
            syntax_errors=[
                SyntaxErrorInfo(
                    file=Path("bad.py"), line=7, message="invalid syntax"
                )
            ],
        )
        result = MockAIProvider().explain(ctx)
        assert "bad.py" in result.root_cause
        assert "7" in result.root_cause or "invalid syntax" in result.root_cause

    def test_syntax_error_confidence_is_high(self, tmp_path: Path) -> None:
        ctx = DiagnosticContext(
            repo_root=tmp_path,
            syntax_errors=[
                SyntaxErrorInfo(file=Path("x.py"), line=1, message="oops")
            ],
        )
        result = MockAIProvider().explain(ctx)
        assert result.confidence == "high"

    def test_issue_without_file_gives_medium_confidence(self, tmp_path: Path) -> None:
        ctx = DiagnosticContext(
            repo_root=tmp_path,
            issues=[
                IssueInfo(
                    issue_id="x",
                    title="Missing README",
                    severity="medium",
                    category="governance",
                    description="No README found.",
                )
            ],
        )
        result = MockAIProvider().explain(ctx)
        assert result.confidence == "medium"

    def test_empty_context_confidence_is_low(self, tmp_path: Path) -> None:
        ctx = DiagnosticContext(repo_root=tmp_path)
        result = MockAIProvider().explain(ctx)
        assert result.confidence == "low"

    def test_affected_components_contain_file(self, tmp_path: Path) -> None:
        ctx = DiagnosticContext(
            repo_root=tmp_path,
            syntax_errors=[
                SyntaxErrorInfo(file=Path("broken.py"), line=3, message="err")
            ],
        )
        result = MockAIProvider().explain(ctx)
        assert any("broken.py" in c for c in result.affected_components)

    def test_dependency_category_fix_mentions_lock_file(self, tmp_path: Path) -> None:
        ctx = DiagnosticContext(
            repo_root=tmp_path,
            issues=[
                IssueInfo(
                    issue_id="dep1",
                    title="No lock file",
                    severity="medium",
                    category="dependency",
                    description="Missing lock file.",
                )
            ],
        )
        result = MockAIProvider().explain(ctx)
        assert "lock" in result.recommended_fix.lower()

    def test_explanation_mentions_project_type(self, tmp_path: Path) -> None:
        ctx = DiagnosticContext(
            repo_root=tmp_path,
            project_types=["JavaScript/TypeScript"],
        )
        result = MockAIProvider().explain(ctx)
        assert "JavaScript/TypeScript" in result.explanation


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_get_analyzer_returns_mock_by_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("REPOMEDIC_AI_PROVIDER", raising=False)
        monkeypatch.delenv("REPOMEDIC_OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        analyzer = get_analyzer()
        assert isinstance(analyzer, MockAIProvider)

    def test_get_analyzer_explicit_mock(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("REPOMEDIC_AI_PROVIDER", raising=False)
        analyzer = get_analyzer(provider="mock")
        assert isinstance(analyzer, MockAIProvider)

    def test_get_analyzer_env_var_selects_mock(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REPOMEDIC_AI_PROVIDER", "mock")
        analyzer = get_analyzer()
        assert isinstance(analyzer, MockAIProvider)

    def test_get_analyzer_unknown_provider_raises_value_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("REPOMEDIC_AI_PROVIDER", raising=False)
        with pytest.raises(ValueError, match="Unknown AI provider"):
            get_analyzer(provider="does_not_exist")

    def test_get_analyzer_unavailable_openai_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # openai package not installed in test env and no key set
        monkeypatch.delenv("REPOMEDIC_OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(ProviderNotAvailableError):
            get_analyzer(provider="openai")


# ---------------------------------------------------------------------------
# AIAnalyzer abstract interface
# ---------------------------------------------------------------------------


class TestAIAnalyzerInterface:
    def test_is_abstract(self) -> None:
        """AIAnalyzer cannot be instantiated directly."""
        with pytest.raises(TypeError):
            AIAnalyzer()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_explain(self) -> None:
        """A subclass without explain() cannot be instantiated."""
        class Incomplete(AIAnalyzer):
            name = "incomplete"

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]

    def test_concrete_subclass_with_explain_works(self) -> None:
        class Minimal(AIAnalyzer):
            name = "minimal"

            def explain(self, context: DiagnosticContext) -> AIExplanation:
                return AIExplanation(
                    root_cause="none",
                    explanation="none",
                    recommended_fix="none",
                    provider="minimal",
                )

        instance = Minimal()
        assert instance.is_available() is True


# ---------------------------------------------------------------------------
# CLI 'explain' command tests
# ---------------------------------------------------------------------------


class TestExplainCommand:
    def test_explain_on_empty_repo(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["explain", str(tmp_path), "--provider", "mock"])
        assert result.exit_code == 0, result.output
        assert "AI Explanation" in result.output or "mock" in result.output.lower()

    def test_explain_json_format(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["explain", str(tmp_path), "--provider", "mock", "--format", "json"],
        )
        assert result.exit_code == 0, result.output
        data = __import__("json").loads(result.output)
        assert "explanation" in data
        assert data["provider"] == "mock"

    def test_explain_with_syntax_error_file(self, tmp_path: Path) -> None:
        broken = tmp_path / "broken.py"
        broken.write_text("def foo(\n", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(cli, ["explain", str(tmp_path), "--provider", "mock"])
        assert result.exit_code == 0, result.output
        # The broken file should appear somewhere in the output
        assert "broken.py" in result.output

    def test_explain_with_focus_note(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "explain",
                str(tmp_path),
                "--provider",
                "mock",
                "--note",
                "Check import cycles",
            ],
        )
        assert result.exit_code == 0, result.output

    def test_explain_with_invalid_provider_exits_nonzero(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli, ["explain", str(tmp_path), "--provider", "nonexistent"]
        )
        assert result.exit_code != 0

    def test_explain_json_structure(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["explain", str(tmp_path), "--provider", "mock", "--format", "json"],
        )
        assert result.exit_code == 0
        import json

        data = json.loads(result.output)
        exp = data["explanation"]
        assert "root_cause" in exp
        assert "explanation" in exp
        assert "recommended_fix" in exp
        assert "affected_components" in exp
        assert "confidence" in exp

    def test_explain_text_contains_sections(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["explain", str(tmp_path), "--provider", "mock"])
        assert result.exit_code == 0
        output = result.output
        assert "Root cause" in output
        assert "Explanation" in output
        assert "Recommended fix" in output


# ---------------------------------------------------------------------------
# _parse_import_target helper
# ---------------------------------------------------------------------------


class TestParseImportTarget:
    def test_plain_import(self) -> None:
        assert _parse_import_target("import os") == "os"

    def test_dotted_import(self) -> None:
        assert _parse_import_target("import os.path") == "os.path"

    def test_import_as(self) -> None:
        assert _parse_import_target("import numpy as np") == "numpy"

    def test_from_import(self) -> None:
        assert _parse_import_target("from pathlib import Path") == "pathlib"

    def test_from_dotted(self) -> None:
        assert _parse_import_target("from os.path import join") == "os.path"

    def test_non_import_returns_none(self) -> None:
        assert _parse_import_target("x = 1") is None
        assert _parse_import_target("# import os") is None
        assert _parse_import_target("") is None
