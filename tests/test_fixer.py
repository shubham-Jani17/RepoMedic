"""Comprehensive tests for the RepoMedic fixing subsystem.

Covers:
- FixSuggestion / FixResult / ApplyReport / VerificationResult models
- templates.render()
- PatchGenerator — missing .gitignore / README / LICENSE / partial sets /
  non-governance issues (unsupported)
- AutoFixer — create success / skip existing / error / dry-run
- FixVerifier — resolved / unresolved / new issues
- CLI fix --suggest / --apply (text and JSON)
- Filesystem error handling
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from repomedic.analyzer.engine import AnalysisEngine
from repomedic.analyzer.models import AnalysisResult, Category, Issue, Severity
from repomedic.cli.main import cli
from repomedic.fixer import (
    ApplyReport,
    AutoFixer,
    FixKind,
    FixResult,
    FixStatus,
    FixSuggestion,
    FixVerifier,
    IssueResolution,
    PatchGenerator,
    VerificationResult,
)
from repomedic.fixer import templates
from repomedic.scanner import FileScanner, ProjectDetector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _governance_issue(
    title: str = "Missing .gitignore",
    severity: Severity = Severity.LOW,
    issue_id: str = "gi000001",
) -> Issue:
    return Issue(
        issue_id=issue_id,
        title=title,
        severity=severity,
        category=Category.GOVERNANCE,
        description=f"Description of {title}",
        recommendation=f"Fix for {title}",
    )


def _non_governance_issue() -> Issue:
    return Issue(
        issue_id="sy000001",
        title="Python syntax error",
        severity=Severity.CRITICAL,
        category=Category.SYNTAX,
        description="Syntax error in foo.py",
        recommendation="Fix the syntax.",
        file=Path("foo.py"),
        line=10,
    )


def _suggestion(
    *,
    issue_id: str = "gi000001",
    issue_title: str = "Missing .gitignore",
    filename: str = ".gitignore",
    content: str = "# gitignore\n",
) -> FixSuggestion:
    return FixSuggestion(
        issue_id=issue_id,
        issue_title=issue_title,
        kind=FixKind.CREATE_FILE,
        target_path=Path(filename),
        content=content,
        rationale="Keeps junk out of git.",
    )


def _make_analysis(root: Path, issues: list[Issue]) -> AnalysisResult:
    result = AnalysisResult(root=root)
    result.issues.extend(issues)
    return result


# ---------------------------------------------------------------------------
# templates
# ---------------------------------------------------------------------------


class TestTemplates:
    def test_render_substitutes_variable(self) -> None:
        out = templates.render("Hello {{NAME}}!", NAME="World")
        assert out == "Hello World!"

    def test_render_multiple_variables(self) -> None:
        out = templates.render(
            "{{YEAR}} {{AUTHOR}}", YEAR="2025", AUTHOR="Alice"
        )
        assert out == "2025 Alice"

    def test_render_unknown_placeholder_left_unchanged(self) -> None:
        out = templates.render("Hello {{UNKNOWN}}!")
        assert "{{UNKNOWN}}" in out

    def test_gitignore_template_is_non_empty(self) -> None:
        assert len(templates.GITIGNORE) > 10

    def test_readme_template_contains_placeholder(self) -> None:
        assert "{{PROJECT_NAME}}" in templates.README_MD

    def test_license_template_contains_placeholders(self) -> None:
        assert "{{YEAR}}" in templates.LICENSE_MIT
        assert "{{AUTHOR}}" in templates.LICENSE_MIT


# ---------------------------------------------------------------------------
# FixSuggestion model
# ---------------------------------------------------------------------------


class TestFixSuggestionModel:
    def test_as_dict_keys(self) -> None:
        s = _suggestion()
        d = s.as_dict()
        assert "issue_id" in d
        assert "target_path" in d
        assert "kind" in d
        assert "rationale" in d
        assert "content_preview" in d

    def test_content_preview_truncated(self) -> None:
        long_content = "x" * 200
        s = _suggestion(content=long_content)
        assert s.as_dict()["content_preview"].endswith("…")

    def test_content_preview_not_truncated_when_short(self) -> None:
        s = _suggestion(content="short")
        assert not s.as_dict()["content_preview"].endswith("…")


# ---------------------------------------------------------------------------
# FixResult / ApplyReport models
# ---------------------------------------------------------------------------


class TestFixResultModel:
    def test_ok_when_created(self) -> None:
        r = FixResult(suggestion=_suggestion(), status=FixStatus.CREATED)
        assert r.ok is True

    def test_ok_when_skipped(self) -> None:
        r = FixResult(suggestion=_suggestion(), status=FixStatus.SKIPPED)
        assert r.ok is True

    def test_not_ok_when_error(self) -> None:
        r = FixResult(
            suggestion=_suggestion(), status=FixStatus.ERROR, message="boom"
        )
        assert r.ok is False

    def test_as_dict_keys(self) -> None:
        r = FixResult(
            suggestion=_suggestion(), status=FixStatus.CREATED, message="created"
        )
        d = r.as_dict()
        assert d["status"] == "created"
        assert d["target_path"] == ".gitignore"


class TestApplyReportModel:
    def test_created_skipped_errors_partitioned(self) -> None:
        report = ApplyReport(
            results=[
                FixResult(_suggestion(filename=".gitignore"), FixStatus.CREATED),
                FixResult(_suggestion(filename="README.md"), FixStatus.SKIPPED),
                FixResult(_suggestion(filename="LICENSE"), FixStatus.ERROR),
            ]
        )
        assert len(report.created) == 1
        assert len(report.skipped) == 1
        assert len(report.errors) == 1

    def test_all_ok_true_when_no_errors(self) -> None:
        report = ApplyReport(
            results=[
                FixResult(_suggestion(), FixStatus.CREATED),
                FixResult(_suggestion(filename="README.md"), FixStatus.SKIPPED),
            ]
        )
        assert report.all_ok is True

    def test_all_ok_false_when_error_present(self) -> None:
        report = ApplyReport(
            results=[
                FixResult(_suggestion(), FixStatus.ERROR, "fail"),
            ]
        )
        assert report.all_ok is False

    def test_as_dict_structure(self) -> None:
        report = ApplyReport(
            results=[FixResult(_suggestion(), FixStatus.CREATED)]
        )
        d = report.as_dict()
        assert d["created_count"] == 1
        assert d["skipped_count"] == 0
        assert d["error_count"] == 0
        assert len(d["results"]) == 1


# ---------------------------------------------------------------------------
# VerificationResult model
# ---------------------------------------------------------------------------


class TestVerificationResultModel:
    def test_all_resolved_true(self) -> None:
        vr = VerificationResult(
            resolutions=[
                IssueResolution("id1", "Missing .gitignore", resolved=True),
                IssueResolution("id2", "Missing README", resolved=True),
            ]
        )
        assert vr.all_resolved is True

    def test_all_resolved_false(self) -> None:
        vr = VerificationResult(
            resolutions=[
                IssueResolution("id1", "Missing .gitignore", resolved=True),
                IssueResolution("id2", "Missing README", resolved=False),
            ]
        )
        assert vr.all_resolved is False

    def test_resolved_unresolved_counts(self) -> None:
        vr = VerificationResult(
            resolutions=[
                IssueResolution("id1", "A", resolved=True),
                IssueResolution("id2", "B", resolved=False),
                IssueResolution("id3", "C", resolved=False),
            ]
        )
        assert vr.resolved_count == 1
        assert vr.unresolved_count == 2

    def test_all_resolved_false_when_empty(self) -> None:
        vr = VerificationResult()
        assert vr.all_resolved is False

    def test_as_dict_structure(self) -> None:
        vr = VerificationResult(
            resolutions=[IssueResolution("x", "Missing README", resolved=True)],
            new_issues_count=0,
        )
        d = vr.as_dict()
        assert d["all_resolved"] is True
        assert d["resolved_count"] == 1
        assert d["unresolved_count"] == 0


# ---------------------------------------------------------------------------
# PatchGenerator
# ---------------------------------------------------------------------------


class TestPatchGeneratorSuggest:
    def test_missing_gitignore_produces_suggestion(self, tmp_path: Path) -> None:
        analysis = _make_analysis(tmp_path, [_governance_issue("Missing .gitignore")])
        suggestions, unsupported = PatchGenerator().generate(analysis)
        assert len(suggestions) == 1
        assert suggestions[0].target_path == Path(".gitignore")
        assert unsupported == []

    def test_missing_readme_produces_suggestion(self, tmp_path: Path) -> None:
        analysis = _make_analysis(
            tmp_path, [_governance_issue("Missing README", issue_id="rm000001")]
        )
        suggestions, _ = PatchGenerator().generate(analysis)
        assert any(s.target_path == Path("README.md") for s in suggestions)

    def test_missing_license_produces_suggestion(self, tmp_path: Path) -> None:
        analysis = _make_analysis(
            tmp_path,
            [_governance_issue("Missing LICENSE", Severity.HIGH, "li000001")],
        )
        suggestions, _ = PatchGenerator().generate(analysis)
        assert any(s.target_path == Path("LICENSE") for s in suggestions)

    def test_all_three_governance_issues(self, tmp_path: Path) -> None:
        analysis = _make_analysis(
            tmp_path,
            [
                _governance_issue("Missing .gitignore", issue_id="gi1"),
                _governance_issue("Missing README", Severity.MEDIUM, "rm1"),
                _governance_issue("Missing LICENSE", Severity.HIGH, "li1"),
            ],
        )
        suggestions, unsupported = PatchGenerator().generate(analysis)
        assert len(suggestions) == 3
        assert unsupported == []

    def test_non_governance_issue_is_unsupported(self, tmp_path: Path) -> None:
        analysis = _make_analysis(tmp_path, [_non_governance_issue()])
        suggestions, unsupported = PatchGenerator().generate(analysis)
        assert suggestions == []
        assert len(unsupported) == 1

    def test_mixed_issues_split_correctly(self, tmp_path: Path) -> None:
        analysis = _make_analysis(
            tmp_path,
            [
                _governance_issue("Missing .gitignore"),
                _non_governance_issue(),
            ],
        )
        suggestions, unsupported = PatchGenerator().generate(analysis)
        assert len(suggestions) == 1
        assert len(unsupported) == 1

    def test_no_issues_returns_empty(self, tmp_path: Path) -> None:
        analysis = _make_analysis(tmp_path, [])
        suggestions, unsupported = PatchGenerator().generate(analysis)
        assert suggestions == []
        assert unsupported == []

    def test_suggestion_does_not_modify_filesystem(self, tmp_path: Path) -> None:
        analysis = _make_analysis(
            tmp_path,
            [
                _governance_issue("Missing .gitignore"),
                _governance_issue("Missing README", Severity.MEDIUM, "rm1"),
                _governance_issue("Missing LICENSE", Severity.HIGH, "li1"),
            ],
        )
        PatchGenerator().generate(analysis)
        # No files should be created
        assert not (tmp_path / ".gitignore").exists()
        assert not (tmp_path / "README.md").exists()
        assert not (tmp_path / "LICENSE").exists()

    def test_project_name_in_readme_content(self, tmp_path: Path) -> None:
        analysis = _make_analysis(
            tmp_path,
            [_governance_issue("Missing README", Severity.MEDIUM, "rm1")],
        )
        generator = PatchGenerator(project_name="MyAwesomeProject")
        suggestions, _ = generator.generate(analysis)
        readme = next(s for s in suggestions if s.target_path == Path("README.md"))
        assert "MyAwesomeProject" in readme.content

    def test_year_and_author_in_license_content(self, tmp_path: Path) -> None:
        analysis = _make_analysis(
            tmp_path,
            [_governance_issue("Missing LICENSE", Severity.HIGH, "li1")],
        )
        generator = PatchGenerator(author="Alice", year="2099")
        suggestions, _ = generator.generate(analysis)
        lic = next(s for s in suggestions if s.target_path == Path("LICENSE"))
        assert "Alice" in lic.content
        assert "2099" in lic.content


# ---------------------------------------------------------------------------
# AutoFixer
# ---------------------------------------------------------------------------


class TestAutoFixerCreate:
    def test_creates_gitignore_when_absent(self, tmp_path: Path) -> None:
        s = _suggestion(filename=".gitignore", content="# gi\n")
        report = AutoFixer(tmp_path).apply([s])
        assert len(report.created) == 1
        assert (tmp_path / ".gitignore").read_text() == "# gi\n"

    def test_creates_readme_when_absent(self, tmp_path: Path) -> None:
        s = _suggestion(filename="README.md", content="# Hello\n")
        report = AutoFixer(tmp_path).apply([s])
        assert len(report.created) == 1
        assert (tmp_path / "README.md").read_text() == "# Hello\n"

    def test_creates_license_when_absent(self, tmp_path: Path) -> None:
        s = _suggestion(filename="LICENSE", content="MIT\n")
        report = AutoFixer(tmp_path).apply([s])
        assert len(report.created) == 1
        assert (tmp_path / "LICENSE").read_text() == "MIT\n"

    def test_creates_all_three(self, tmp_path: Path) -> None:
        suggestions = [
            _suggestion(filename=".gitignore", content="gi"),
            _suggestion(filename="README.md", content="rm", issue_id="rm1"),
            _suggestion(filename="LICENSE", content="li", issue_id="li1"),
        ]
        report = AutoFixer(tmp_path).apply(suggestions)
        assert len(report.created) == 3
        assert len(report.skipped) == 0
        assert len(report.errors) == 0

    def test_result_message_mentions_path(self, tmp_path: Path) -> None:
        s = _suggestion(filename=".gitignore")
        report = AutoFixer(tmp_path).apply([s])
        assert ".gitignore" in report.created[0].message


class TestAutoFixerSkip:
    def test_skips_existing_gitignore(self, tmp_path: Path) -> None:
        (tmp_path / ".gitignore").write_text("# existing\n")
        s = _suggestion(filename=".gitignore", content="# new content\n")
        report = AutoFixer(tmp_path).apply([s])
        assert len(report.skipped) == 1
        # Content must NOT be overwritten
        assert (tmp_path / ".gitignore").read_text() == "# existing\n"

    def test_skips_existing_readme(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# existing\n")
        s = _suggestion(filename="README.md", content="# new\n", issue_id="rm1")
        report = AutoFixer(tmp_path).apply([s])
        assert len(report.skipped) == 1
        assert (tmp_path / "README.md").read_text() == "# existing\n"

    def test_skips_existing_license(self, tmp_path: Path) -> None:
        (tmp_path / "LICENSE").write_text("Apache 2.0\n")
        s = _suggestion(filename="LICENSE", content="MIT\n", issue_id="li1")
        report = AutoFixer(tmp_path).apply([s])
        assert len(report.skipped) == 1

    def test_partial_existing_only_skips_present(self, tmp_path: Path) -> None:
        (tmp_path / ".gitignore").write_text("# existing\n")
        suggestions = [
            _suggestion(filename=".gitignore", content="new"),
            _suggestion(filename="README.md", content="rm", issue_id="rm1"),
        ]
        report = AutoFixer(tmp_path).apply(suggestions)
        assert len(report.created) == 1
        assert len(report.skipped) == 1
        assert report.created[0].suggestion.target_path == Path("README.md")
        assert report.skipped[0].suggestion.target_path == Path(".gitignore")

    def test_skip_message_mentions_path(self, tmp_path: Path) -> None:
        (tmp_path / ".gitignore").write_text("# existing\n")
        s = _suggestion(filename=".gitignore")
        report = AutoFixer(tmp_path).apply([s])
        assert ".gitignore" in report.skipped[0].message


class TestAutoFixerDryRun:
    def test_dry_run_does_not_create_files(self, tmp_path: Path) -> None:
        s = _suggestion(filename=".gitignore")
        report = AutoFixer(tmp_path, dry_run=True).apply([s])
        assert not (tmp_path / ".gitignore").exists()
        # Result is still CREATED (what would happen)
        assert len(report.created) == 1

    def test_dry_run_skips_existing(self, tmp_path: Path) -> None:
        (tmp_path / ".gitignore").write_text("# existing\n")
        s = _suggestion(filename=".gitignore")
        report = AutoFixer(tmp_path, dry_run=True).apply([s])
        assert len(report.skipped) == 1

    def test_dry_run_message_indicates_dry_run(self, tmp_path: Path) -> None:
        s = _suggestion(filename=".gitignore")
        report = AutoFixer(tmp_path, dry_run=True).apply([s])
        assert "dry-run" in report.created[0].message.lower()


class TestAutoFixerErrors:
    def test_empty_suggestions_returns_empty_report(self, tmp_path: Path) -> None:
        report = AutoFixer(tmp_path).apply([])
        assert report.results == []

    def test_unsupported_kind_returns_error(self, tmp_path: Path) -> None:
        s = FixSuggestion(
            issue_id="x",
            issue_title="x",
            kind=FixKind.CREATE_FILE,  # we'll patch kind to invalid
            target_path=Path("x.txt"),
            content="x",
            rationale="x",
        )
        # Manually override enum value to simulate unsupported kind
        object.__setattr__(s, "kind", "delete_file")  # type: ignore[arg-type]
        report = AutoFixer(tmp_path).apply([s])
        assert len(report.errors) == 1

    @pytest.mark.skipif(sys.platform == "win32", reason="chmod not reliable on Windows")
    def test_permission_error_produces_error_result(self, tmp_path: Path) -> None:
        """Simulate a permission error by making the directory read-only."""
        locked = tmp_path / "locked"
        locked.mkdir()
        locked.chmod(stat.S_IRUSR | stat.S_IXUSR)  # read + execute, no write
        try:
            s = _suggestion(filename="locked/.gitignore")
            report = AutoFixer(tmp_path).apply([s])
            assert len(report.errors) == 1
            assert "permission" in report.errors[0].message.lower()
        finally:
            locked.chmod(stat.S_IRWXU)

    def test_oserror_produces_error_result(self, tmp_path: Path) -> None:
        """Simulate a generic OSError by patching Path.write_text."""
        s = _suggestion(filename=".gitignore")
        with patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
            report = AutoFixer(tmp_path).apply([s])
        assert len(report.errors) == 1
        assert "disk full" in report.errors[0].message


# ---------------------------------------------------------------------------
# FixVerifier — full integration
# ---------------------------------------------------------------------------


class TestFixVerifier:
    def test_resolved_when_file_created(self, tmp_path: Path) -> None:
        """Creating .gitignore should make the Missing .gitignore issue disappear."""
        # Initial analysis: no .gitignore
        scan = FileScanner().scan(tmp_path)
        proj = ProjectDetector().detect(scan)
        before = AnalysisEngine().run(scan, proj)

        gi_issues = [i for i in before.issues if "gitignore" in i.title.lower()]
        assert gi_issues, "Expected a Missing .gitignore issue before the fix"

        # Apply the fix
        generator = PatchGenerator()
        suggestions, _ = generator.generate(before)
        gi_suggestions = [
            s for s in suggestions if s.target_path == Path(".gitignore")
        ]
        report = AutoFixer(tmp_path).apply(gi_suggestions)
        assert report.created  # must have been created

        # Verify
        verifier = FixVerifier(tmp_path)
        result = verifier.verify(before, report)

        gi_resolutions = [
            r for r in result.resolutions if "gitignore" in r.issue_title.lower()
        ]
        assert gi_resolutions
        assert gi_resolutions[0].resolved is True

    def test_unresolved_when_file_not_created(self, tmp_path: Path) -> None:
        """Skipped fixes should show as unresolved."""
        # Pre-create .gitignore so it already exists
        (tmp_path / ".gitignore").write_text("# existing\n")

        scan = FileScanner().scan(tmp_path)
        proj = ProjectDetector().detect(scan)
        before = AnalysisEngine().run(scan, proj)

        # Manually build an issue and suggestion that will be SKIPPED
        fake_issue = _governance_issue("Missing .gitignore", issue_id="gi_fake")
        before.issues.append(fake_issue)
        fake_suggestion = _suggestion(filename=".gitignore", issue_id="gi_fake")

        # AutoFixer will SKIP because the file already exists
        report = AutoFixer(tmp_path).apply([fake_suggestion])
        assert report.skipped  # not created

        verifier = FixVerifier(tmp_path)
        result = verifier.verify(before, report)
        # No CREATED results → no resolutions tracked
        assert result.resolutions == []

    def test_no_new_issues_after_governance_fix(self, tmp_path: Path) -> None:
        """Applying a governance fix should not introduce new issues."""
        scan = FileScanner().scan(tmp_path)
        proj = ProjectDetector().detect(scan)
        before = AnalysisEngine().run(scan, proj)

        generator = PatchGenerator()
        suggestions, _ = generator.generate(before)
        report = AutoFixer(tmp_path).apply(suggestions)

        verifier = FixVerifier(tmp_path)
        result = verifier.verify(before, report)
        assert result.new_issues_count == 0

    def test_all_three_governance_fixes_verified(self, tmp_path: Path) -> None:
        """All three governance issues should resolve after --apply."""
        scan = FileScanner().scan(tmp_path)
        proj = ProjectDetector().detect(scan)
        before = AnalysisEngine().run(scan, proj)

        generator = PatchGenerator()
        suggestions, _ = generator.generate(before)
        report = AutoFixer(tmp_path).apply(suggestions)

        verifier = FixVerifier(tmp_path)
        result = verifier.verify(before, report)

        assert result.all_resolved is True

    def test_empty_report_returns_empty_verification(self, tmp_path: Path) -> None:
        before = _make_analysis(tmp_path, [])
        report = ApplyReport()
        verifier = FixVerifier(tmp_path)
        result = verifier.verify(before, report)
        assert result.resolutions == []
        assert result.new_issues_count == 0


# ---------------------------------------------------------------------------
# CLI fix --suggest
# ---------------------------------------------------------------------------


class TestCLIFixSuggest:
    def test_suggest_on_empty_repo_exits_zero(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["fix", "--suggest", str(tmp_path)])
        assert result.exit_code == 0, result.output

    def test_suggest_does_not_create_files(self, tmp_path: Path) -> None:
        runner = CliRunner()
        runner.invoke(cli, ["fix", "--suggest", str(tmp_path)])
        assert not (tmp_path / ".gitignore").exists()
        assert not (tmp_path / "README.md").exists()
        assert not (tmp_path / "LICENSE").exists()

    def test_suggest_shows_fix_entries(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["fix", "--suggest", str(tmp_path)])
        assert result.exit_code == 0
        # Should list at least .gitignore
        assert ".gitignore" in result.output

    def test_suggest_json_format(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli, ["fix", "--suggest", "--format", "json", str(tmp_path)]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["mode"] == "suggest"
        assert "suggestions" in data
        assert "unsupported_count" in data

    def test_suggest_json_no_files_created(self, tmp_path: Path) -> None:
        runner = CliRunner()
        runner.invoke(cli, ["fix", "--suggest", "--format", "json", str(tmp_path)])
        assert not (tmp_path / ".gitignore").exists()

    def test_suggest_with_all_files_present_shows_no_fixes(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / ".gitignore").write_text("# gi\n")
        (tmp_path / "README.md").write_text("# rm\n")
        (tmp_path / "LICENSE").write_text("MIT\n")
        runner = CliRunner()
        result = runner.invoke(
            cli, ["fix", "--suggest", "--format", "json", str(tmp_path)]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        # All files present → no governance issues → no suggestions
        assert data["suggestions"] == []

    def test_default_mode_is_suggest(self, tmp_path: Path) -> None:
        """Running fix with no flags should behave like --suggest."""
        runner = CliRunner()
        result = runner.invoke(cli, ["fix", str(tmp_path)])
        assert result.exit_code == 0
        assert not (tmp_path / ".gitignore").exists()


# ---------------------------------------------------------------------------
# CLI fix --apply
# ---------------------------------------------------------------------------


class TestCLIFixApply:
    def test_apply_creates_governance_files(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["fix", "--apply", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert (tmp_path / ".gitignore").exists()
        assert (tmp_path / "README.md").exists()
        assert (tmp_path / "LICENSE").exists()

    def test_apply_shows_created_files(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["fix", "--apply", str(tmp_path)])
        assert ".gitignore" in result.output
        assert "README.md" in result.output
        assert "LICENSE" in result.output

    def test_apply_skips_existing_files(self, tmp_path: Path) -> None:
        (tmp_path / ".gitignore").write_text("# existing\n")
        runner = CliRunner()
        result = runner.invoke(cli, ["fix", "--apply", str(tmp_path)])
        assert result.exit_code == 0
        # Content must not be overwritten
        assert (tmp_path / ".gitignore").read_text() == "# existing\n"

    def test_apply_json_format(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli, ["fix", "--apply", "--format", "json", str(tmp_path)]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["mode"] == "apply"
        assert "apply_report" in data
        assert "verification" in data

    def test_apply_json_verification_all_resolved(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli, ["fix", "--apply", "--format", "json", str(tmp_path)]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["verification"]["all_resolved"] is True

    def test_apply_idempotent_second_run_creates_nothing(self, tmp_path: Path) -> None:
        runner = CliRunner()
        runner.invoke(cli, ["fix", "--apply", str(tmp_path)])
        # Second run — all governance files exist, so no issues → no suggestions
        result = runner.invoke(
            cli, ["fix", "--apply", "--format", "json", str(tmp_path)]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["apply_report"]["created_count"] == 0
        assert data["apply_report"]["error_count"] == 0

    def test_apply_verification_shows_in_text_output(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["fix", "--apply", str(tmp_path)])
        # Verification section should be present
        assert "Verification" in result.output or "resolved" in result.output.lower()

    def test_apply_partial_existing_partial_created(self, tmp_path: Path) -> None:
        """Pre-existing README.md means that issue is absent; only .gitignore
        and LICENSE are created."""
        (tmp_path / "README.md").write_text("# existing\n")
        runner = CliRunner()
        result = runner.invoke(
            cli, ["fix", "--apply", "--format", "json", str(tmp_path)]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        # .gitignore and LICENSE were missing → created; README was present → no issue
        assert data["apply_report"]["created_count"] == 2
        assert data["apply_report"]["skipped_count"] == 0
        assert (tmp_path / ".gitignore").exists()
        assert (tmp_path / "LICENSE").exists()
        assert (tmp_path / "README.md").read_text() == "# existing\n"
