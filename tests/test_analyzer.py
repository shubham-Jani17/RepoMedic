"""Tests for analyzer models, all concrete analyzers, engine, and CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from repomedic.analyzer.dependency import DependencyAnalyzer
from repomedic.analyzer.engine import AnalysisEngine
from repomedic.analyzer.error import ErrorAnalyzer
from repomedic.analyzer.governance import GovernanceAnalyzer
from repomedic.analyzer.models import (
    AnalysisResult,
    Category,
    Issue,
    Severity,
)
from repomedic.analyzer.syntax import SyntaxAnalyzer
from repomedic.cli.main import cli
from repomedic.scanner import FileScanner, ProjectDetector
from repomedic.scanner.models import ScanResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_files(tmp_path: Path, **files: str) -> Path:
    """Create named files with given content under tmp_path."""
    for name, content in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return tmp_path


def scan_and_detect(path: Path):
    scan_result = FileScanner().scan(path)
    proj_result = ProjectDetector().detect(scan_result)
    return scan_result, proj_result


def run_analyzer(analyzer, path: Path) -> AnalysisResult:
    scan_result, proj_result = scan_and_detect(path)
    result = AnalysisResult(root=path)
    analyzer.analyze(scan_result, proj_result, result)
    return result


# ---------------------------------------------------------------------------
# Issue and AnalysisResult models
# ---------------------------------------------------------------------------


class TestIssueModel:
    def test_as_dict_keys(self) -> None:
        issue = Issue(
            title="Test",
            severity=Severity.HIGH,
            category=Category.SYNTAX,
            description="desc",
            recommendation="rec",
            file=Path("main.py"),
            line=10,
        )
        d = issue.as_dict()
        assert set(d.keys()) == {
            "issue_id", "title", "severity", "category",
            "file", "line", "description", "recommendation",
        }
        assert d["severity"] == "high"
        assert d["category"] == "syntax"
        assert d["file"] == "main.py"
        assert d["line"] == 10

    def test_auto_issue_id(self) -> None:
        a = Issue(title="A", severity=Severity.INFO, category=Category.OTHER,
                  description="", recommendation="")
        b = Issue(title="B", severity=Severity.INFO, category=Category.OTHER,
                  description="", recommendation="")
        assert a.issue_id != b.issue_id
        assert len(a.issue_id) == 8

    def test_no_file_no_line(self) -> None:
        issue = Issue(title="T", severity=Severity.LOW, category=Category.GOVERNANCE,
                      description="d", recommendation="r")
        assert issue.file is None
        assert issue.line is None
        assert issue.as_dict()["file"] is None


class TestSeverityOrdering:
    def test_order(self) -> None:
        assert Severity.INFO < Severity.LOW
        assert Severity.LOW < Severity.MEDIUM
        assert Severity.MEDIUM < Severity.HIGH
        assert Severity.HIGH < Severity.CRITICAL

    def test_ge(self) -> None:
        assert Severity.HIGH >= Severity.MEDIUM
        assert Severity.INFO >= Severity.INFO

    def test_le(self) -> None:
        assert Severity.LOW <= Severity.CRITICAL


class TestAnalysisResult:
    def _make_result(self, tmp_path: Path) -> AnalysisResult:
        r = AnalysisResult(root=tmp_path)
        r.issues = [
            Issue(title="A", severity=Severity.CRITICAL, category=Category.SYNTAX,
                  description="", recommendation=""),
            Issue(title="B", severity=Severity.LOW, category=Category.GOVERNANCE,
                  description="", recommendation=""),
            Issue(title="C", severity=Severity.CRITICAL, category=Category.SYNTAX,
                  description="", recommendation=""),
        ]
        return r

    def test_issue_count(self, tmp_path: Path) -> None:
        r = self._make_result(tmp_path)
        assert r.issue_count == 3

    def test_by_severity(self, tmp_path: Path) -> None:
        r = self._make_result(tmp_path)
        assert len(r.by_severity(Severity.CRITICAL)) == 2
        assert len(r.by_severity(Severity.LOW)) == 1

    def test_by_category(self, tmp_path: Path) -> None:
        r = self._make_result(tmp_path)
        assert len(r.by_category(Category.SYNTAX)) == 2

    def test_has_critical(self, tmp_path: Path) -> None:
        r = self._make_result(tmp_path)
        assert r.has_critical

    def test_severity_counts(self, tmp_path: Path) -> None:
        r = self._make_result(tmp_path)
        counts = r.severity_counts()
        assert counts["critical"] == 2
        assert counts["low"] == 1
        assert counts["info"] == 0

    def test_sort_issues_highest_first(self, tmp_path: Path) -> None:
        r = self._make_result(tmp_path)
        r.sort_issues()
        assert r.issues[0].severity == Severity.CRITICAL
        assert r.issues[-1].severity == Severity.LOW


# ---------------------------------------------------------------------------
# SyntaxAnalyzer
# ---------------------------------------------------------------------------


class TestSyntaxAnalyzer:
    def test_clean_file_no_issues(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"clean.py": "def hello():\n    return 42\n"})
        result = run_analyzer(SyntaxAnalyzer(), tmp_path)
        syntax_issues = result.by_category(Category.SYNTAX)
        assert syntax_issues == []
        assert result.errors == []

    def test_syntax_error_detected(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"bad.py": "def broken(\n    return 1\n"})
        result = run_analyzer(SyntaxAnalyzer(), tmp_path)
        issues = result.by_category(Category.SYNTAX)
        assert len(issues) == 1
        assert issues[0].severity == Severity.CRITICAL
        assert issues[0].file == Path("bad.py")
        assert issues[0].line is not None

    def test_syntax_error_has_file_reference(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"errors/broken.py": "class Foo\n    pass\n"})
        result = run_analyzer(SyntaxAnalyzer(), tmp_path)
        issues = result.by_category(Category.SYNTAX)
        assert any("broken.py" in str(i.file) for i in issues)

    def test_multiple_bad_files(self, tmp_path: Path) -> None:
        make_files(
            tmp_path,
            **{
                "a.py": "def ok(): pass",
                "b.py": "def broken(\n    pass",
                "c.py": "class Also(Bad",
            },
        )
        result = run_analyzer(SyntaxAnalyzer(), tmp_path)
        issues = result.by_category(Category.SYNTAX)
        assert len(issues) == 2

    def test_non_python_files_skipped(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"bad.js": "function({"})
        result = run_analyzer(SyntaxAnalyzer(), tmp_path)
        assert result.by_category(Category.SYNTAX) == []

    def test_empty_python_file_no_issue(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"empty.py": ""})
        result = run_analyzer(SyntaxAnalyzer(), tmp_path)
        assert result.by_category(Category.SYNTAX) == []

    def test_unclosed_paren_token_error(self, tmp_path: Path) -> None:
        # ast.parse catches this; ensure we get exactly one issue
        make_files(tmp_path, **{"unclosed.py": "x = (1 + 2\n"})
        result = run_analyzer(SyntaxAnalyzer(), tmp_path)
        issues = result.by_category(Category.SYNTAX)
        assert len(issues) == 1

    def test_recommendation_present(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"bad.py": "def bad(\n"})
        result = run_analyzer(SyntaxAnalyzer(), tmp_path)
        assert result.issues[0].recommendation != ""


# ---------------------------------------------------------------------------
# GovernanceAnalyzer
# ---------------------------------------------------------------------------


class TestGovernanceAnalyzer:
    def test_all_missing(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"main.py": "pass"})
        result = run_analyzer(GovernanceAnalyzer(), tmp_path)
        gov = result.by_category(Category.GOVERNANCE)
        titles = {i.title for i in gov}
        assert "Missing README" in titles
        assert "Missing LICENSE" in titles
        assert "Missing .gitignore" in titles

    def test_readme_present_suppresses_issue(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"README.md": "# Hello", "main.py": "pass"})
        result = run_analyzer(GovernanceAnalyzer(), tmp_path)
        gov = result.by_category(Category.GOVERNANCE)
        assert not any(i.title == "Missing README" for i in gov)

    def test_readme_rst_accepted(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"README.rst": "Title\n====="})
        result = run_analyzer(GovernanceAnalyzer(), tmp_path)
        gov = result.by_category(Category.GOVERNANCE)
        assert not any(i.title == "Missing README" for i in gov)

    def test_license_present(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"LICENSE": "MIT"})
        result = run_analyzer(GovernanceAnalyzer(), tmp_path)
        assert not any(i.title == "Missing LICENSE" for i in result.issues)

    def test_gitignore_present(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{".gitignore": "__pycache__/"})
        result = run_analyzer(GovernanceAnalyzer(), tmp_path)
        assert not any(i.title == "Missing .gitignore" for i in result.issues)

    def test_severity_levels(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"main.py": "pass"})
        result = run_analyzer(GovernanceAnalyzer(), tmp_path)
        sev_map = {i.title: i.severity for i in result.by_category(Category.GOVERNANCE)}
        assert sev_map["Missing LICENSE"] == Severity.HIGH
        assert sev_map["Missing README"] == Severity.MEDIUM
        assert sev_map["Missing .gitignore"] == Severity.LOW

    def test_full_governance_suite_no_issues(self, tmp_path: Path) -> None:
        make_files(
            tmp_path,
            **{
                "README.md": "# Repo",
                "LICENSE": "MIT",
                ".gitignore": "*.pyc",
                "main.py": "pass",
            },
        )
        result = run_analyzer(GovernanceAnalyzer(), tmp_path)
        assert result.by_category(Category.GOVERNANCE) == []


# ---------------------------------------------------------------------------
# DependencyAnalyzer
# ---------------------------------------------------------------------------


class TestDependencyAnalyzer:
    def test_node_package_json_no_lockfile(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"package.json": "{}"})
        result = run_analyzer(DependencyAnalyzer(), tmp_path)
        dep = result.by_category(Category.DEPENDENCY)
        assert any("package.json" in i.title for i in dep)
        assert any(i.severity == Severity.MEDIUM for i in dep)

    def test_node_with_npm_lock_no_issue(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"package.json": "{}", "package-lock.json": "{}"})
        result = run_analyzer(DependencyAnalyzer(), tmp_path)
        dep = result.by_category(Category.DEPENDENCY)
        assert not any("package.json without a lock" in i.title for i in dep)

    def test_node_with_yarn_lock_no_issue(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"package.json": "{}", "yarn.lock": ""})
        result = run_analyzer(DependencyAnalyzer(), tmp_path)
        dep = result.by_category(Category.DEPENDENCY)
        assert not any("package.json without a lock" in i.title for i in dep)

    def test_rust_cargo_no_lockfile(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"Cargo.toml": "[package]", "src/main.rs": "fn main() {}"})
        result = run_analyzer(DependencyAnalyzer(), tmp_path)
        dep = result.by_category(Category.DEPENDENCY)
        assert any("Cargo.lock" in i.title for i in dep)

    def test_rust_with_lockfile_no_issue(self, tmp_path: Path) -> None:
        make_files(
            tmp_path,
            **{"Cargo.toml": "[package]", "Cargo.lock": "", "src/main.rs": "fn main() {}"},
        )
        result = run_analyzer(DependencyAnalyzer(), tmp_path)
        dep = result.by_category(Category.DEPENDENCY)
        assert not any("Cargo.lock" in i.title for i in dep)

    def test_python_pyproject_no_lock(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"pyproject.toml": "[project]", "app.py": "pass"})
        result = run_analyzer(DependencyAnalyzer(), tmp_path)
        dep = result.by_category(Category.DEPENDENCY)
        assert any("pyproject.toml" in i.title for i in dep)

    def test_no_manifests_no_dep_issues(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"main.py": "pass"})
        result = run_analyzer(DependencyAnalyzer(), tmp_path)
        assert result.by_category(Category.DEPENDENCY) == []


# ---------------------------------------------------------------------------
# ErrorAnalyzer
# ---------------------------------------------------------------------------


class TestErrorAnalyzer:
    def test_todo_detected(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"app.py": "# TODO: fix this\npass\n"})
        result = run_analyzer(ErrorAnalyzer(), tmp_path)
        assert any("TODO" in i.title for i in result.issues)

    def test_fixme_detected(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"app.py": "x = 1  # FIXME: broken\n"})
        result = run_analyzer(ErrorAnalyzer(), tmp_path)
        assert any("FIXME" in i.title for i in result.issues)

    def test_bare_except_detected(self, tmp_path: Path) -> None:
        code = "try:\n    pass\nexcept:\n    pass\n"
        make_files(tmp_path, **{"app.py": code})
        result = run_analyzer(ErrorAnalyzer(), tmp_path)
        assert any("Bare except" in i.title for i in result.issues)
        bare = next(i for i in result.issues if "Bare except" in i.title)
        assert bare.severity == Severity.MEDIUM
        assert bare.line == 3

    def test_debug_print_detected(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"app.py": "print('debug value')\n"})
        result = run_analyzer(ErrorAnalyzer(), tmp_path)
        assert any("print()" in i.title for i in result.issues)

    def test_console_log_in_js(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"app.js": "console.log('hi');\n"})
        result = run_analyzer(ErrorAnalyzer(), tmp_path)
        assert any("console.log" in i.title for i in result.issues)

    def test_console_log_in_ts(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"app.ts": "console.log('debug');\n"})
        result = run_analyzer(ErrorAnalyzer(), tmp_path)
        assert any("console.log" in i.title for i in result.issues)

    def test_clean_file_no_issues(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"clean.py": "def hello():\n    return 42\n"})
        result = run_analyzer(ErrorAnalyzer(), tmp_path)
        assert result.issues == []

    def test_non_source_file_skipped(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"data.csv": "# TODO: remove this\n"})
        result = run_analyzer(ErrorAnalyzer(), tmp_path)
        assert result.issues == []

    def test_todo_cap_per_file(self, tmp_path: Path) -> None:
        # More than 5 TODOs in one file — should be capped
        lines = "\n".join(f"# TODO item {i}" for i in range(10))
        make_files(tmp_path, **{"lots.py": lines})
        result = run_analyzer(ErrorAnalyzer(), tmp_path)
        todo_issues = [i for i in result.issues if "TODO" in i.title]
        assert len(todo_issues) <= 5

    def test_issue_has_line_number(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"app.py": "pass\n# TODO: line 2\n"})
        result = run_analyzer(ErrorAnalyzer(), tmp_path)
        todo = next(i for i in result.issues if "TODO" in i.title)
        assert todo.line == 2


# ---------------------------------------------------------------------------
# AnalysisEngine
# ---------------------------------------------------------------------------


class TestAnalysisEngine:
    def test_default_analyzers_run(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"main.py": "pass"})
        scan_result, proj_result = scan_and_detect(tmp_path)
        engine = AnalysisEngine()
        result = engine.run(scan_result, proj_result)
        assert isinstance(result, AnalysisResult)
        # Governance issues should always appear for a bare repo
        assert result.issue_count > 0

    def test_issues_sorted_by_severity(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"bad.py": "def broken(\n"})
        scan_result, proj_result = scan_and_detect(tmp_path)
        result = AnalysisEngine().run(scan_result, proj_result)
        severities = [_SEVERITY_ORDER(i.severity) for i in result.issues]
        # sorted descending
        assert severities == sorted(severities, reverse=True)

    def test_custom_analyzer_list(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"main.py": "pass"})
        scan_result, proj_result = scan_and_detect(tmp_path)
        engine = AnalysisEngine(analyzers=[GovernanceAnalyzer()])  # type: ignore[list-item]
        result = engine.run(scan_result, proj_result)
        # Only governance issues — no syntax, no dep, no error-pattern issues
        cats = {i.category for i in result.issues}
        assert cats == {Category.GOVERNANCE} or cats == set()

    def test_broken_analyzer_does_not_abort(self, tmp_path: Path) -> None:
        class CrashingAnalyzer:
            name = "Crasher"
            def analyze(self, *_):
                raise RuntimeError("intentional crash")

        make_files(tmp_path, **{"main.py": "pass"})
        scan_result, proj_result = scan_and_detect(tmp_path)
        engine = AnalysisEngine(analyzers=[CrashingAnalyzer(), GovernanceAnalyzer()])  # type: ignore[list-item]
        result = engine.run(scan_result, proj_result)
        # Error recorded, but governance still ran
        assert any("Crasher" in e for e in result.errors)
        assert result.by_category(Category.GOVERNANCE)

    def test_analyzer_names(self, tmp_path: Path) -> None:
        engine = AnalysisEngine()
        names = engine.analyzer_names
        assert "SyntaxAnalyzer" in names
        assert "GovernanceAnalyzer" in names

    def test_empty_repo_runs_without_error(self, tmp_path: Path) -> None:
        scan_result, proj_result = scan_and_detect(tmp_path)
        result = AnalysisEngine().run(scan_result, proj_result)
        assert result.errors == []


def _SEVERITY_ORDER(s: Severity) -> int:
    return {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}[s.value]


# ---------------------------------------------------------------------------
# CLI analyze command
# ---------------------------------------------------------------------------


class TestAnalyzeCLI:
    def test_analyze_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["analyze", "--help"])
        assert result.exit_code == 0
        assert "--format" in result.output
        assert "--min-severity" in result.output

    def test_analyze_text_output(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"main.py": "pass"})
        runner = CliRunner()
        result = runner.invoke(cli, ["analyze", str(tmp_path)])
        assert result.exit_code == 0
        assert "Analysis results" in result.output

    def test_analyze_json_output(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"main.py": "pass"})
        runner = CliRunner()
        result = runner.invoke(cli, ["analyze", "--format", "json", str(tmp_path)])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert "issues" in payload
        assert "severity_counts" in payload
        assert "issue_count" in payload

    def test_analyze_finds_syntax_error(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"bad.py": "def broken(\n"})
        runner = CliRunner()
        result = runner.invoke(cli, ["analyze", "--format", "json", str(tmp_path)])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        cats = [i["category"] for i in payload["issues"]]
        assert "syntax" in cats

    def test_analyze_finds_governance_issues(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"main.py": "pass"})
        runner = CliRunner()
        result = runner.invoke(cli, ["analyze", "--format", "json", str(tmp_path)])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        cats = [i["category"] for i in payload["issues"]]
        assert "governance" in cats

    def test_analyze_min_severity_filters(self, tmp_path: Path) -> None:
        make_files(tmp_path, **{"main.py": "pass"})
        runner = CliRunner()
        result = runner.invoke(
            cli, ["analyze", "--format", "json", "--min-severity", "high", str(tmp_path)]
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        for issue in payload["issues"]:
            assert issue["severity"] in ("high", "critical")

    def test_analyze_invalid_path(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["analyze", "/no/such/path/xyz"])
        assert result.exit_code != 0

    def test_analyze_defaults_to_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        make_files(tmp_path, **{"main.py": "pass"})
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["analyze"])
        assert result.exit_code == 0

    def test_analyze_all_good_repo(self, tmp_path: Path) -> None:
        """A complete repo with README/LICENSE/.gitignore and clean code."""
        make_files(
            tmp_path,
            **{
                "README.md": "# My Project",
                "LICENSE": "MIT",
                ".gitignore": "*.pyc",
                "main.py": "def hello():\n    return 42\n",
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["analyze", "--format", "json", "--min-severity", "medium", str(tmp_path)],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        # No medium+ governance issues, and no syntax issues
        for issue in payload["issues"]:
            assert issue["severity"] not in ("info", "low")
        gov_issues = [i for i in payload["issues"] if i["category"] == "governance"]
        assert gov_issues == []
