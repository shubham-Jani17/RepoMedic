"""Comprehensive tests for the RepoMedic reporting subsystem.

Covers:
- HealthScoreCalculator — deductions, boundaries, status labels
- ReportData model — as_dict() structure
- ReportBuilder — correct field population
- TerminalReporter — key sections present
- JSONReporter — valid JSON, required fields, issue normalisation
- CLI repomedic report (text and --json modes)
- Healthy / warning / error repository scenarios
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from repomedic.analyzer.engine import AnalysisEngine
from repomedic.analyzer.models import AnalysisResult, Category, Issue, Severity
from repomedic.cli.main import cli
from repomedic.reporter import (
    DEDUCTIONS,
    HealthScoreCalculator,
    JSONReporter,
    ReportBuilder,
    ReportData,
    TerminalReporter,
)
from repomedic.reporter.builder import ReportBuilder
from repomedic.scanner import FileScanner, LanguageDetector, ProjectDetector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_issue(
    severity: Severity,
    category: Category = Category.GOVERNANCE,
    title: str = "",
    issue_id: str = "t0000001",
    file: Path | None = None,
    line: int | None = None,
) -> Issue:
    title = title or f"Test {severity.value} issue"
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


def _analysis_with(
    root: Path,
    issues: list[Issue] | None = None,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
) -> AnalysisResult:
    a = AnalysisResult(root=root)
    a.issues = list(issues or [])
    a.errors = list(errors or [])
    a.warnings = list(warnings or [])
    return a


def _full_pipeline(tmp_path: Path):
    """Run the full scan/detect/analyse pipeline on *tmp_path*."""
    scan = FileScanner().scan(tmp_path)
    proj = ProjectDetector().detect(scan)
    lang = LanguageDetector().detect(scan)
    analysis = AnalysisEngine().run(scan, proj)
    return scan, proj, lang, analysis


def _render_text(data: ReportData, show_all: bool = True) -> str:
    buf = io.StringIO()
    TerminalReporter(stream=buf, show_all_issues=show_all).render(data)
    return buf.getvalue()


def _render_json(data: ReportData) -> dict:
    buf = io.StringIO()
    JSONReporter(stream=buf).render(data)
    return json.loads(buf.getvalue())


# ---------------------------------------------------------------------------
# HealthScoreCalculator
# ---------------------------------------------------------------------------


class TestHealthScoreCalculator:
    def test_perfect_score_with_no_issues(self, tmp_path: Path) -> None:
        analysis = _analysis_with(tmp_path)
        score = HealthScoreCalculator().score(analysis)
        assert score == 100

    def test_critical_deducts_20(self, tmp_path: Path) -> None:
        analysis = _analysis_with(tmp_path, [_make_issue(Severity.CRITICAL)])
        score = HealthScoreCalculator().score(analysis)
        assert score == 100 - DEDUCTIONS[Severity.CRITICAL]
        assert score == 80

    def test_high_deducts_10(self, tmp_path: Path) -> None:
        analysis = _analysis_with(tmp_path, [_make_issue(Severity.HIGH)])
        score = HealthScoreCalculator().score(analysis)
        assert score == 90

    def test_medium_deducts_5(self, tmp_path: Path) -> None:
        analysis = _analysis_with(tmp_path, [_make_issue(Severity.MEDIUM)])
        score = HealthScoreCalculator().score(analysis)
        assert score == 95

    def test_low_deducts_2(self, tmp_path: Path) -> None:
        analysis = _analysis_with(tmp_path, [_make_issue(Severity.LOW)])
        score = HealthScoreCalculator().score(analysis)
        assert score == 98

    def test_info_deducts_1(self, tmp_path: Path) -> None:
        analysis = _analysis_with(tmp_path, [_make_issue(Severity.INFO)])
        score = HealthScoreCalculator().score(analysis)
        assert score == 99

    def test_multiple_issues_accumulate(self, tmp_path: Path) -> None:
        issues = [
            _make_issue(Severity.HIGH, issue_id="h1"),
            _make_issue(Severity.HIGH, issue_id="h2"),
            _make_issue(Severity.MEDIUM, issue_id="m1"),
        ]
        analysis = _analysis_with(tmp_path, issues)
        score = HealthScoreCalculator().score(analysis)
        # 100 - 10 - 10 - 5 = 75
        assert score == 75

    def test_score_clamped_to_zero(self, tmp_path: Path) -> None:
        # 6 CRITICAL issues → 100 - 120 = -20, should clamp to 0
        issues = [
            _make_issue(Severity.CRITICAL, issue_id=f"c{i}")
            for i in range(6)
        ]
        analysis = _analysis_with(tmp_path, issues)
        score = HealthScoreCalculator().score(analysis)
        assert score == 0

    def test_score_never_exceeds_100(self, tmp_path: Path) -> None:
        analysis = _analysis_with(tmp_path)
        score = HealthScoreCalculator().score(analysis)
        assert score <= 100

    def test_analyzer_error_deducts_5(self, tmp_path: Path) -> None:
        analysis = _analysis_with(tmp_path, errors=["SomeAnalyzer crashed"])
        score = HealthScoreCalculator().score(analysis)
        assert score == 95

    def test_two_analyzer_errors_deduct_10(self, tmp_path: Path) -> None:
        analysis = _analysis_with(tmp_path, errors=["err1", "err2"])
        score = HealthScoreCalculator().score(analysis)
        assert score == 90

    def test_issues_and_errors_combine(self, tmp_path: Path) -> None:
        analysis = _analysis_with(
            tmp_path,
            issues=[_make_issue(Severity.HIGH)],
            errors=["crash"],
        )
        # 100 - 10 (HIGH) - 5 (error) = 85
        score = HealthScoreCalculator().score(analysis)
        assert score == 85

    def test_deterministic_same_input(self, tmp_path: Path) -> None:
        issues = [
            _make_issue(Severity.HIGH, issue_id="h1"),
            _make_issue(Severity.MEDIUM, issue_id="m1"),
        ]
        analysis = _analysis_with(tmp_path, issues)
        calc = HealthScoreCalculator()
        assert calc.score(analysis) == calc.score(analysis)

    # Status labels
    def test_status_healthy_at_100(self) -> None:
        assert HealthScoreCalculator.status(100) == "healthy"

    def test_status_healthy_at_90(self) -> None:
        assert HealthScoreCalculator.status(90) == "healthy"

    def test_status_warning_at_89(self) -> None:
        assert HealthScoreCalculator.status(89) == "warning"

    def test_status_warning_at_60(self) -> None:
        assert HealthScoreCalculator.status(60) == "warning"

    def test_status_error_at_59(self) -> None:
        assert HealthScoreCalculator.status(59) == "error"

    def test_status_error_at_0(self) -> None:
        assert HealthScoreCalculator.status(0) == "error"

    def test_deductions_constant_has_all_severities(self) -> None:
        for sev in Severity:
            assert sev in DEDUCTIONS


# ---------------------------------------------------------------------------
# ReportData model
# ---------------------------------------------------------------------------


class TestReportDataModel:
    def test_as_dict_has_required_keys(self, tmp_path: Path) -> None:
        data = ReportData(repo_root=tmp_path)
        d = data.as_dict()
        required = {
            "repository", "status", "health_score", "total_issues",
            "total_errors", "verification_status", "issues",
        }
        assert required <= set(d.keys())

    def test_as_dict_repository_is_string(self, tmp_path: Path) -> None:
        data = ReportData(repo_root=tmp_path)
        assert isinstance(data.as_dict()["repository"], str)

    def test_default_values(self, tmp_path: Path) -> None:
        data = ReportData(repo_root=tmp_path)
        assert data.health_score == 100
        assert data.status == "healthy"
        assert data.total_issues == 0
        assert data.total_errors == 0
        assert data.verification_status == "not_run"
        assert data.governance_status == "ok"
        assert data.issues == []


# ---------------------------------------------------------------------------
# ReportBuilder
# ---------------------------------------------------------------------------


class TestReportBuilder:
    def test_healthy_empty_repo(self, tmp_path: Path) -> None:
        # Give it governance files so no issues appear
        (tmp_path / ".gitignore").write_text("# gi\n")
        (tmp_path / "README.md").write_text("# r\n")
        (tmp_path / "LICENSE").write_text("MIT\n")
        scan, proj, lang, analysis = _full_pipeline(tmp_path)
        data = ReportBuilder(scan, proj, lang, analysis).build()
        assert data.health_score == 100
        assert data.status == "healthy"
        assert data.total_issues == 0
        assert data.governance_status == "ok"

    def test_missing_governance_files_reflected(self, tmp_path: Path) -> None:
        scan, proj, lang, analysis = _full_pipeline(tmp_path)
        data = ReportBuilder(scan, proj, lang, analysis).build()
        assert data.governance_status == "missing_files"
        assert data.total_issues > 0

    def test_score_decreases_with_issues(self, tmp_path: Path) -> None:
        scan, proj, lang, analysis = _full_pipeline(tmp_path)
        data = ReportBuilder(scan, proj, lang, analysis).build()
        assert data.health_score < 100

    def test_issue_list_populated(self, tmp_path: Path) -> None:
        scan, proj, lang, analysis = _full_pipeline(tmp_path)
        data = ReportBuilder(scan, proj, lang, analysis).build()
        assert len(data.issues) == data.total_issues
        for issue in data.issues:
            assert "issue_id" in issue
            assert "severity" in issue

    def test_errors_populated(self, tmp_path: Path) -> None:
        scan, proj, lang, analysis = _full_pipeline(tmp_path)
        analysis.errors.append("fake error")
        data = ReportBuilder(scan, proj, lang, analysis).build()
        assert data.total_errors == 1
        assert "fake error" in data.errors

    def test_warnings_populated(self, tmp_path: Path) -> None:
        scan, proj, lang, analysis = _full_pipeline(tmp_path)
        analysis.warnings.append("fake warning")
        data = ReportBuilder(scan, proj, lang, analysis).build()
        assert data.total_warnings == 1
        assert "fake warning" in data.warnings

    def test_languages_list(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("x = 1\n")
        scan, proj, lang, analysis = _full_pipeline(tmp_path)
        data = ReportBuilder(scan, proj, lang, analysis).build()
        assert "Python" in data.languages

    def test_verification_status_default_not_run(self, tmp_path: Path) -> None:
        scan, proj, lang, analysis = _full_pipeline(tmp_path)
        data = ReportBuilder(scan, proj, lang, analysis).build()
        assert data.verification_status == "not_run"


# ---------------------------------------------------------------------------
# TerminalReporter
# ---------------------------------------------------------------------------


class TestTerminalReporter:
    def _report(self, tmp_path: Path, *, show_all: bool = True) -> str:
        scan, proj, lang, analysis = _full_pipeline(tmp_path)
        data = ReportBuilder(scan, proj, lang, analysis).build()
        return _render_text(data, show_all=show_all)

    def test_output_contains_health_score(self, tmp_path: Path) -> None:
        output = self._report(tmp_path)
        assert "Health score" in output or "health" in output.lower()

    def test_output_contains_repository_path(self, tmp_path: Path) -> None:
        output = self._report(tmp_path)
        assert str(tmp_path) in output

    def test_output_contains_total_issues(self, tmp_path: Path) -> None:
        output = self._report(tmp_path)
        assert "Total issues" in output or "issues" in output.lower()

    def test_output_contains_verification_status(self, tmp_path: Path) -> None:
        output = self._report(tmp_path)
        assert "Verification" in output

    def test_output_contains_governance_status(self, tmp_path: Path) -> None:
        output = self._report(tmp_path)
        assert "Governance" in output

    def test_healthy_repo_shows_healthy(self, tmp_path: Path) -> None:
        (tmp_path / ".gitignore").write_text("# gi\n")
        (tmp_path / "README.md").write_text("# r\n")
        (tmp_path / "LICENSE").write_text("MIT\n")
        output = self._report(tmp_path)
        assert "HEALTHY" in output.upper()

    def test_warning_repo_shows_warning(self, tmp_path: Path) -> None:
        # Missing LICENSE (HIGH = −10) and README (MEDIUM = −5) → 85 → warning
        (tmp_path / ".gitignore").write_text("# gi\n")
        output = self._report(tmp_path)
        assert "WARNING" in output.upper() or "ERROR" in output.upper()

    def test_issues_shown_by_default(self, tmp_path: Path) -> None:
        output = self._report(tmp_path, show_all=True)
        # At least one governance issue should appear
        assert "Missing" in output or "MEDIUM" in output.upper() or "HIGH" in output.upper()

    def test_issue_contains_title(self, tmp_path: Path) -> None:
        data = ReportData(
            repo_root=tmp_path,
            health_score=75,
            status="warning",
            total_issues=1,
            issues=[{
                "issue_id": "x1",
                "title": "Unique Issue Title XYZ",
                "severity": "high",
                "category": "governance",
                "description": "desc",
                "recommendation": "fix",
                "file": None,
                "line": None,
            }],
        )
        output = _render_text(data)
        assert "Unique Issue Title XYZ" in output

    def test_error_section_shown_when_errors_present(self, tmp_path: Path) -> None:
        data = ReportData(
            repo_root=tmp_path,
            total_errors=1,
            errors=["SomeAnalyzer crashed: something"],
        )
        output = _render_text(data)
        assert "SomeAnalyzer crashed" in output

    def test_warning_section_shown_when_warnings_present(self, tmp_path: Path) -> None:
        data = ReportData(
            repo_root=tmp_path,
            total_warnings=1,
            warnings=["Could not read file: foo.py"],
        )
        output = _render_text(data)
        assert "Could not read file" in output

    def test_low_severity_hidden_by_default(self, tmp_path: Path) -> None:
        data = ReportData(
            repo_root=tmp_path,
            total_issues=1,
            issues=[{
                "issue_id": "lo1",
                "title": "LowSeverityIssueXYZ",
                "severity": "low",
                "category": "governance",
                "description": "desc",
                "recommendation": "fix",
                "file": None,
                "line": None,
            }],
        )
        buf = io.StringIO()
        TerminalReporter(stream=buf, show_all_issues=False).render(data)
        assert "LowSeverityIssueXYZ" not in buf.getvalue()

    def test_low_severity_shown_with_all_issues_flag(self, tmp_path: Path) -> None:
        data = ReportData(
            repo_root=tmp_path,
            total_issues=1,
            issues=[{
                "issue_id": "lo1",
                "title": "LowSeverityIssueXYZ",
                "severity": "low",
                "category": "governance",
                "description": "desc",
                "recommendation": "fix",
                "file": None,
                "line": None,
            }],
        )
        buf = io.StringIO()
        TerminalReporter(stream=buf, show_all_issues=True).render(data)
        assert "LowSeverityIssueXYZ" in buf.getvalue()

    def test_issue_with_file_and_line_shown(self, tmp_path: Path) -> None:
        data = ReportData(
            repo_root=tmp_path,
            total_issues=1,
            issues=[{
                "issue_id": "sy1",
                "title": "Python syntax error",
                "severity": "critical",
                "category": "syntax",
                "description": "bad",
                "recommendation": "fix",
                "file": "src/foo.py",
                "line": 42,
            }],
        )
        output = _render_text(data)
        assert "src/foo.py" in output
        assert "42" in output

    def test_language_list_shown(self, tmp_path: Path) -> None:
        (tmp_path / "app.py").write_text("x=1\n")
        scan, proj, lang, analysis = _full_pipeline(tmp_path)
        data = ReportBuilder(scan, proj, lang, analysis).build()
        output = _render_text(data)
        assert "Python" in output


# ---------------------------------------------------------------------------
# JSONReporter
# ---------------------------------------------------------------------------


class TestJSONReporter:
    def test_output_is_valid_json(self, tmp_path: Path) -> None:
        scan, proj, lang, analysis = _full_pipeline(tmp_path)
        data = ReportBuilder(scan, proj, lang, analysis).build()
        result = _render_json(data)
        assert isinstance(result, dict)

    def test_required_top_level_keys(self, tmp_path: Path) -> None:
        scan, proj, lang, analysis = _full_pipeline(tmp_path)
        data = ReportBuilder(scan, proj, lang, analysis).build()
        result = _render_json(data)
        for key in (
            "repository", "status", "health_score", "total_issues",
            "total_errors", "verification_status", "issues",
        ):
            assert key in result, f"Missing key: {key}"

    def test_repository_is_string(self, tmp_path: Path) -> None:
        scan, proj, lang, analysis = _full_pipeline(tmp_path)
        data = ReportBuilder(scan, proj, lang, analysis).build()
        result = _render_json(data)
        assert isinstance(result["repository"], str)

    def test_health_score_is_int(self, tmp_path: Path) -> None:
        scan, proj, lang, analysis = _full_pipeline(tmp_path)
        data = ReportBuilder(scan, proj, lang, analysis).build()
        result = _render_json(data)
        assert isinstance(result["health_score"], int)
        assert 0 <= result["health_score"] <= 100

    def test_issues_is_list(self, tmp_path: Path) -> None:
        scan, proj, lang, analysis = _full_pipeline(tmp_path)
        data = ReportBuilder(scan, proj, lang, analysis).build()
        result = _render_json(data)
        assert isinstance(result["issues"], list)

    def test_issue_fields_present(self, tmp_path: Path) -> None:
        scan, proj, lang, analysis = _full_pipeline(tmp_path)
        data = ReportBuilder(scan, proj, lang, analysis).build()
        result = _render_json(data)
        for issue in result["issues"]:
            for field in ("id", "title", "severity", "category",
                          "description", "recommendation", "file", "line"):
                assert field in issue, f"Issue missing field: {field}"

    def test_file_and_line_are_none_when_absent(self, tmp_path: Path) -> None:
        data = ReportData(
            repo_root=tmp_path,
            issues=[{
                "issue_id": "g1",
                "title": "Missing README",
                "severity": "medium",
                "category": "governance",
                "description": "desc",
                "recommendation": "fix",
            }],
        )
        result = _render_json(data)
        assert result["issues"][0]["file"] is None
        assert result["issues"][0]["line"] is None

    def test_file_and_line_present_when_set(self, tmp_path: Path) -> None:
        data = ReportData(
            repo_root=tmp_path,
            issues=[{
                "issue_id": "sy1",
                "title": "Syntax error",
                "severity": "critical",
                "category": "syntax",
                "description": "d",
                "recommendation": "r",
                "file": "src/bad.py",
                "line": 10,
            }],
        )
        result = _render_json(data)
        issue = result["issues"][0]
        assert issue["file"] == "src/bad.py"
        assert issue["line"] == 10

    def test_healthy_repo_score_100(self, tmp_path: Path) -> None:
        (tmp_path / ".gitignore").write_text("# gi\n")
        (tmp_path / "README.md").write_text("# r\n")
        (tmp_path / "LICENSE").write_text("MIT\n")
        scan, proj, lang, analysis = _full_pipeline(tmp_path)
        data = ReportBuilder(scan, proj, lang, analysis).build()
        result = _render_json(data)
        assert result["health_score"] == 100
        assert result["status"] == "healthy"

    def test_error_repo_score_low(self, tmp_path: Path) -> None:
        # Six CRITICAL issues → score 0
        issues = [
            _make_issue(Severity.CRITICAL, issue_id=f"c{i}") for i in range(6)
        ]
        data = ReportData(
            repo_root=tmp_path,
            health_score=0,
            status="error",
            total_issues=6,
            issues=[i.as_dict() for i in issues],
        )
        result = _render_json(data)
        assert result["health_score"] == 0
        assert result["status"] == "error"

    def test_json_to_file(self, tmp_path: Path) -> None:
        out = tmp_path / "report.json"
        scan, proj, lang, analysis = _full_pipeline(tmp_path)
        data = ReportBuilder(scan, proj, lang, analysis).build()
        with open(out, "w", encoding="utf-8") as f:
            JSONReporter(stream=f).render(data)
        content = json.loads(out.read_text())
        assert content["repository"]

    def test_json_output_stable_serialisation(self, tmp_path: Path) -> None:
        """Calling render() twice on the same data produces identical output."""
        scan, proj, lang, analysis = _full_pipeline(tmp_path)
        data = ReportBuilder(scan, proj, lang, analysis).build()
        out1 = io.StringIO()
        out2 = io.StringIO()
        JSONReporter(stream=out1).render(data)
        JSONReporter(stream=out2).render(data)
        assert out1.getvalue() == out2.getvalue()


# ---------------------------------------------------------------------------
# Health score boundaries (table-driven)
# ---------------------------------------------------------------------------


class TestHealthScoreBoundaries:
    @pytest.mark.parametrize("score,expected_status", [
        (100, "healthy"),
        (90, "healthy"),
        (89, "warning"),
        (60, "warning"),
        (59, "error"),
        (1, "error"),
        (0, "error"),
    ])
    def test_boundary(self, score: int, expected_status: str) -> None:
        assert HealthScoreCalculator.status(score) == expected_status

    def test_score_exact_deduction_five_criticals(self, tmp_path: Path) -> None:
        issues = [_make_issue(Severity.CRITICAL, issue_id=f"c{i}") for i in range(5)]
        analysis = _analysis_with(tmp_path, issues)
        score = HealthScoreCalculator().score(analysis)
        assert score == 0  # 100 - 5*20 = 0

    def test_score_exact_deduction_mixed(self, tmp_path: Path) -> None:
        # 1 HIGH (−10) + 2 MEDIUM (−10) + 3 LOW (−6) = −26 → 74
        issues = (
            [_make_issue(Severity.HIGH, issue_id="h0")]
            + [_make_issue(Severity.MEDIUM, issue_id=f"m{i}") for i in range(2)]
            + [_make_issue(Severity.LOW, issue_id=f"l{i}") for i in range(3)]
        )
        analysis = _analysis_with(tmp_path, issues)
        score = HealthScoreCalculator().score(analysis)
        assert score == 74


# ---------------------------------------------------------------------------
# CLI report command
# ---------------------------------------------------------------------------


class TestCLIReport:
    def test_text_report_exits_zero(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["report", str(tmp_path)])
        assert result.exit_code == 0, result.output

    def test_text_report_contains_health_score(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["report", str(tmp_path)])
        assert "health" in result.output.lower() or "score" in result.output.lower()

    def test_json_report_exits_zero(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["report", "--json", str(tmp_path)])
        assert result.exit_code == 0, result.output

    def test_json_report_is_valid_json(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["report", "--json", str(tmp_path)])
        data = json.loads(result.output)
        assert isinstance(data, dict)

    def test_json_report_has_required_fields(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["report", "--json", str(tmp_path)])
        data = json.loads(result.output)
        for key in ("repository", "status", "health_score",
                    "total_issues", "total_errors", "verification_status", "issues"):
            assert key in data, f"Missing key: {key}"

    def test_json_report_issues_have_id_field(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["report", "--json", str(tmp_path)])
        data = json.loads(result.output)
        for issue in data["issues"]:
            assert "id" in issue

    def test_json_healthy_repo(self, tmp_path: Path) -> None:
        (tmp_path / ".gitignore").write_text("# gi\n")
        (tmp_path / "README.md").write_text("# r\n")
        (tmp_path / "LICENSE").write_text("MIT\n")
        runner = CliRunner()
        result = runner.invoke(cli, ["report", "--json", str(tmp_path)])
        data = json.loads(result.output)
        assert data["health_score"] == 100
        assert data["status"] == "healthy"
        assert data["total_issues"] == 0

    def test_json_warning_repo(self, tmp_path: Path) -> None:
        # Only .gitignore present — LICENSE (HIGH −10) + README (MEDIUM −5) missing → 85
        (tmp_path / ".gitignore").write_text("# gi\n")
        runner = CliRunner()
        result = runner.invoke(cli, ["report", "--json", str(tmp_path)])
        data = json.loads(result.output)
        assert data["health_score"] < 100
        assert data["status"] in ("warning", "error")

    def test_json_error_repo(self, tmp_path: Path) -> None:
        # Empty repo: missing LICENSE (HIGH), README (MEDIUM), .gitignore (LOW)
        # 100 - 10 - 5 - 2 = 83 → warning (not "error" territory at this scale)
        # For "error" we'd need many more issues; just check score drops
        runner = CliRunner()
        result = runner.invoke(cli, ["report", "--json", str(tmp_path)])
        data = json.loads(result.output)
        assert data["total_issues"] >= 3

    def test_output_to_file(self, tmp_path: Path) -> None:
        out = tmp_path / "out.json"
        runner = CliRunner()
        result = runner.invoke(
            cli, ["report", "--json", str(tmp_path), "-o", str(out)]
        )
        assert result.exit_code == 0
        content = json.loads(out.read_text())
        assert content["health_score"] is not None

    def test_all_issues_flag_text(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["report", "--all-issues", str(tmp_path)])
        assert result.exit_code == 0
