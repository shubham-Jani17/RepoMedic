"""Tests for the repository validation system.

Covers:
- healthy repository (PASS)
- low health score (FAIL)
- blocking error (FAIL due to CRITICAL issue)
- Git repository detection
- non-Git repository handling
- changed files detection
- blast radius calculation
- PASS verdict
- FAIL verdict
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from repomedic.analyzer.models import AnalysisResult, Category, Issue, Severity
from repomedic.cli.main import cli
from repomedic.graph.graph import DependencyGraph
from repomedic.scanner.models import FileEntry, ScanResult
from repomedic.validator import GitChangesDetector, RepositoryValidator, ValidationResult
from repomedic.validator.models import ValidationResult as ValidationResultModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scan(tmp_path: Path) -> ScanResult:
    """Return a minimal ScanResult rooted at *tmp_path*."""
    return ScanResult(root=tmp_path, files=[], errors=[])


def _make_analysis(root: Path, issues: list[Issue] | None = None) -> AnalysisResult:
    return AnalysisResult(root=root, issues=issues or [])


def _critical_issue() -> Issue:
    return Issue(
        title="Critical security vulnerability",
        severity=Severity.CRITICAL,
        category=Category.SECURITY,
        description="Remote code execution via eval()",
        recommendation="Remove eval()",
        issue_id="crit-001",
    )


def _high_issue() -> Issue:
    return Issue(
        title="High severity issue",
        severity=Severity.HIGH,
        category=Category.SYNTAX,
        description="Syntax problem",
        recommendation="Fix it",
        issue_id="high-001",
    )


# ---------------------------------------------------------------------------
# ValidationResult model tests
# ---------------------------------------------------------------------------


class TestValidationResultModel:
    def test_defaults(self, tmp_path: Path) -> None:
        result = ValidationResultModel(repo_root=tmp_path)
        assert result.health_score == 100
        assert result.threshold == 0
        assert result.blocking_errors == []
        assert result.changed_files == []
        assert result.affected_files == []
        assert result.blast_radius == 0
        assert result.passed is True

    def test_as_dict(self, tmp_path: Path) -> None:
        result = ValidationResultModel(
            repo_root=tmp_path,
            health_score=75,
            threshold=80,
            passed=False,
        )
        d = result.as_dict()
        assert d["health_score"] == 75
        assert d["threshold"] == 80
        assert d["passed"] is False
        assert d["repo_root"] == str(tmp_path)


# ---------------------------------------------------------------------------
# GitChangesDetector tests
# ---------------------------------------------------------------------------


class TestGitChangesDetector:
    def test_non_git_repo_is_not_git(self, tmp_path: Path) -> None:
        detector = GitChangesDetector(tmp_path)
        # Simulate git reporting it is NOT inside a work tree
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stdout="")
            assert detector.is_git_repo() is False

    def test_non_git_repo_changed_files_empty(self, tmp_path: Path) -> None:
        detector = GitChangesDetector(tmp_path)
        with patch.object(detector, "is_git_repo", return_value=False):
            assert detector.changed_files() == []

    def test_is_git_repo_returns_true_when_git_confirms(self, tmp_path: Path) -> None:
        detector = GitChangesDetector(tmp_path)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="true\n")
            assert detector.is_git_repo() is True

    def test_is_git_repo_returns_false_on_oserror(self, tmp_path: Path) -> None:
        detector = GitChangesDetector(tmp_path)
        with patch("subprocess.run", side_effect=OSError("git not found")):
            assert detector.is_git_repo() is False

    def test_changed_files_returns_sorted_union(self, tmp_path: Path) -> None:
        detector = GitChangesDetector(tmp_path)

        def _mock_run(cmd, **kwargs):
            mock = MagicMock()
            mock.returncode = 0
            if "--cached" in cmd:
                mock.stdout = "staged.py\n"
            elif "ls-files" in cmd:
                mock.stdout = "untracked.py\n"
            else:
                mock.stdout = "modified.py\n"
            return mock

        with patch.object(detector, "is_git_repo", return_value=True):
            with patch("subprocess.run", side_effect=_mock_run):
                files = detector.changed_files()
        assert "modified.py" in files
        assert "staged.py" in files
        assert "untracked.py" in files
        assert files == sorted(files)

    def test_changed_files_deduplicates(self, tmp_path: Path) -> None:
        detector = GitChangesDetector(tmp_path)

        def _mock_run(cmd, **kwargs):
            mock = MagicMock()
            mock.returncode = 0
            # Same file appears in staged and unstaged
            mock.stdout = "dup.py\n"
            return mock

        with patch.object(detector, "is_git_repo", return_value=True):
            with patch("subprocess.run", side_effect=_mock_run):
                files = detector.changed_files()
        assert files.count("dup.py") == 1

    def test_git_timeout_returns_empty(self, tmp_path: Path) -> None:
        detector = GitChangesDetector(tmp_path)
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 10)):
            assert detector.is_git_repo() is False


# ---------------------------------------------------------------------------
# RepositoryValidator unit tests  (pipeline internals mocked)
# ---------------------------------------------------------------------------


class TestRepositoryValidatorUnit:
    """Test the validator logic by mocking the pipeline components."""

    def _make_validator(self, threshold: int = 0) -> RepositoryValidator:
        return RepositoryValidator(threshold=threshold)

    @patch("repomedic.validator.validator.GitChangesDetector")
    @patch("repomedic.validator.validator.AnalysisEngine")
    @patch("repomedic.validator.validator.ProjectDetector")
    @patch("repomedic.validator.validator.FileScanner")
    def test_healthy_repository_passes(
        self, mock_scanner, mock_proj, mock_engine, mock_git, tmp_path: Path
    ) -> None:
        """A repository with no issues and score=100 should PASS."""
        _setup_mocks(mock_scanner, mock_proj, mock_engine, mock_git, tmp_path, issues=[])
        result = self._make_validator(threshold=80).validate(tmp_path)
        assert result.passed is True
        assert result.health_score == 100

    @patch("repomedic.validator.validator.GitChangesDetector")
    @patch("repomedic.validator.validator.AnalysisEngine")
    @patch("repomedic.validator.validator.ProjectDetector")
    @patch("repomedic.validator.validator.FileScanner")
    def test_low_health_score_fails(
        self, mock_scanner, mock_proj, mock_engine, mock_git, tmp_path: Path
    ) -> None:
        """A repository with score < threshold should FAIL."""
        # Ten HIGH issues → score = 100 - 10*10 = 0
        issues = [_high_issue() for _ in range(10)]
        _setup_mocks(mock_scanner, mock_proj, mock_engine, mock_git, tmp_path, issues=issues)
        result = self._make_validator(threshold=80).validate(tmp_path)
        assert result.passed is False
        assert result.health_score < 80

    @patch("repomedic.validator.validator.GitChangesDetector")
    @patch("repomedic.validator.validator.AnalysisEngine")
    @patch("repomedic.validator.validator.ProjectDetector")
    @patch("repomedic.validator.validator.FileScanner")
    def test_blocking_error_fails_regardless_of_score(
        self, mock_scanner, mock_proj, mock_engine, mock_git, tmp_path: Path
    ) -> None:
        """A CRITICAL issue must cause FAIL even if score >= threshold."""
        _setup_mocks(
            mock_scanner, mock_proj, mock_engine, mock_git, tmp_path,
            issues=[_critical_issue()]
        )
        result = self._make_validator(threshold=0).validate(tmp_path)
        assert result.passed is False
        assert len(result.blocking_errors) == 1

    @patch("repomedic.validator.validator.GitChangesDetector")
    @patch("repomedic.validator.validator.AnalysisEngine")
    @patch("repomedic.validator.validator.ProjectDetector")
    @patch("repomedic.validator.validator.FileScanner")
    def test_no_threshold_passes_if_no_blocking_errors(
        self, mock_scanner, mock_proj, mock_engine, mock_git, tmp_path: Path
    ) -> None:
        """With threshold=0, only blocking errors can cause FAIL."""
        issues = [_high_issue()]  # HIGH is not blocking
        _setup_mocks(mock_scanner, mock_proj, mock_engine, mock_git, tmp_path, issues=issues)
        result = self._make_validator(threshold=0).validate(tmp_path)
        assert result.passed is True

    @patch("repomedic.validator.validator.GitChangesDetector")
    @patch("repomedic.validator.validator.AnalysisEngine")
    @patch("repomedic.validator.validator.ProjectDetector")
    @patch("repomedic.validator.validator.FileScanner")
    def test_git_repo_sets_is_git_true(
        self, mock_scanner, mock_proj, mock_engine, mock_git, tmp_path: Path
    ) -> None:
        """is_git_repo must be True when GitChangesDetector says so."""
        _setup_mocks(
            mock_scanner, mock_proj, mock_engine, mock_git, tmp_path,
            issues=[], is_git=True, changed=["foo.py"]
        )
        result = self._make_validator().validate(tmp_path)
        assert result.is_git_repo is True
        assert "foo.py" in result.changed_files

    @patch("repomedic.validator.validator.GitChangesDetector")
    @patch("repomedic.validator.validator.AnalysisEngine")
    @patch("repomedic.validator.validator.ProjectDetector")
    @patch("repomedic.validator.validator.FileScanner")
    def test_non_git_repo_no_crash(
        self, mock_scanner, mock_proj, mock_engine, mock_git, tmp_path: Path
    ) -> None:
        """Non-Git repos must be handled gracefully — no changed files, no crash."""
        _setup_mocks(
            mock_scanner, mock_proj, mock_engine, mock_git, tmp_path,
            issues=[], is_git=False, changed=[]
        )
        result = self._make_validator().validate(tmp_path)
        assert result.is_git_repo is False
        assert result.changed_files == []

    @patch("repomedic.validator.validator.build_graph_from_scan")
    @patch("repomedic.validator.validator.GitChangesDetector")
    @patch("repomedic.validator.validator.AnalysisEngine")
    @patch("repomedic.validator.validator.ProjectDetector")
    @patch("repomedic.validator.validator.FileScanner")
    def test_changed_files_triggers_blast_radius(
        self, mock_scanner, mock_proj, mock_engine, mock_git, mock_graph_factory,
        tmp_path: Path,
    ) -> None:
        """When changed files exist, blast radius must be calculated."""
        _setup_mocks(
            mock_scanner, mock_proj, mock_engine, mock_git, tmp_path,
            issues=[], is_git=True, changed=["a.py"]
        )
        # Build a graph where a.py has one downstream dependent
        graph = DependencyGraph()
        graph.add_edge("b.py", "a.py")  # b imports a → a change affects b
        mock_graph_factory.return_value = graph

        result = self._make_validator().validate(tmp_path)
        assert "b.py" in result.affected_files
        assert result.blast_radius == 1

    @patch("repomedic.validator.validator.build_graph_from_scan")
    @patch("repomedic.validator.validator.GitChangesDetector")
    @patch("repomedic.validator.validator.AnalysisEngine")
    @patch("repomedic.validator.validator.ProjectDetector")
    @patch("repomedic.validator.validator.FileScanner")
    def test_no_changed_files_skips_blast_radius(
        self, mock_scanner, mock_proj, mock_engine, mock_git, mock_graph_factory,
        tmp_path: Path,
    ) -> None:
        """When no changed files exist, blast radius should be 0 and graph not built."""
        _setup_mocks(
            mock_scanner, mock_proj, mock_engine, mock_git, tmp_path,
            issues=[], is_git=True, changed=[]
        )
        result = self._make_validator().validate(tmp_path)
        assert result.blast_radius == 0
        assert result.affected_files == []
        mock_graph_factory.assert_not_called()

    @patch("repomedic.validator.validator.GitChangesDetector")
    @patch("repomedic.validator.validator.AnalysisEngine")
    @patch("repomedic.validator.validator.ProjectDetector")
    @patch("repomedic.validator.validator.FileScanner")
    def test_pass_verdict(
        self, mock_scanner, mock_proj, mock_engine, mock_git, tmp_path: Path
    ) -> None:
        _setup_mocks(mock_scanner, mock_proj, mock_engine, mock_git, tmp_path, issues=[])
        result = self._make_validator(threshold=50).validate(tmp_path)
        assert result.passed is True

    @patch("repomedic.validator.validator.GitChangesDetector")
    @patch("repomedic.validator.validator.AnalysisEngine")
    @patch("repomedic.validator.validator.ProjectDetector")
    @patch("repomedic.validator.validator.FileScanner")
    def test_fail_verdict(
        self, mock_scanner, mock_proj, mock_engine, mock_git, tmp_path: Path
    ) -> None:
        issues = [_critical_issue()]
        _setup_mocks(mock_scanner, mock_proj, mock_engine, mock_git, tmp_path, issues=issues)
        result = self._make_validator(threshold=50).validate(tmp_path)
        assert result.passed is False


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestValidateCLI:
    def test_validate_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", "--help"])
        assert result.exit_code == 0
        assert "--fail-under" in result.output

    def test_validate_pass_exit_code_zero(self, tmp_path: Path) -> None:
        """Healthy repository with no threshold exits 0."""
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", str(tmp_path)])
        assert result.exit_code == 0

    def test_validate_fail_under_passes_when_score_above(self, tmp_path: Path) -> None:
        """With an empty repo (score=100) and --fail-under 50, should PASS."""
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", str(tmp_path), "--fail-under", "50"])
        assert result.exit_code == 0
        assert "PASS" in result.output

    @patch("repomedic.cli.commands.validate.RepositoryValidator")
    def test_validate_fail_under_fails_when_score_below(
        self, mock_validator_cls, tmp_path: Path
    ) -> None:
        """When score is below threshold, CLI exits 1."""
        mock_result = ValidationResult(
            repo_root=tmp_path,
            health_score=40,
            threshold=80,
            passed=False,
        )
        mock_validator_cls.return_value.validate.return_value = mock_result

        runner = CliRunner()
        result = runner.invoke(cli, ["validate", str(tmp_path), "--fail-under", "80"])
        assert result.exit_code == 1
        assert "FAIL" in result.output

    @patch("repomedic.cli.commands.validate.RepositoryValidator")
    def test_validate_blocking_error_causes_fail(
        self, mock_validator_cls, tmp_path: Path
    ) -> None:
        """Blocking errors cause exit code 1."""
        mock_result = ValidationResult(
            repo_root=tmp_path,
            health_score=80,
            threshold=0,
            blocking_errors=["[abc] Critical vulnerability"],
            passed=False,
        )
        mock_validator_cls.return_value.validate.return_value = mock_result

        runner = CliRunner()
        result = runner.invoke(cli, ["validate", str(tmp_path)])
        assert result.exit_code == 1
        assert "FAIL" in result.output
        assert "Critical vulnerability" in result.output

    @patch("repomedic.cli.commands.validate.RepositoryValidator")
    def test_output_shows_health_score(
        self, mock_validator_cls, tmp_path: Path
    ) -> None:
        mock_result = ValidationResult(
            repo_root=tmp_path,
            health_score=87,
            threshold=80,
            passed=True,
        )
        mock_validator_cls.return_value.validate.return_value = mock_result

        runner = CliRunner()
        result = runner.invoke(cli, ["validate", str(tmp_path), "--fail-under", "80"])
        assert "87" in result.output
        assert "PASS" in result.output

    @patch("repomedic.cli.commands.validate.RepositoryValidator")
    def test_output_shows_changed_and_affected_files(
        self, mock_validator_cls, tmp_path: Path
    ) -> None:
        mock_result = ValidationResult(
            repo_root=tmp_path,
            health_score=100,
            threshold=0,
            is_git_repo=True,
            changed_files=["src/a.py"],
            affected_files=["src/b.py"],
            blast_radius=1,
            passed=True,
        )
        mock_validator_cls.return_value.validate.return_value = mock_result

        runner = CliRunner()
        result = runner.invoke(cli, ["validate", str(tmp_path)])
        assert "src/a.py" in result.output
        assert "src/b.py" in result.output
        assert "1" in result.output

    @patch("repomedic.cli.commands.validate.RepositoryValidator")
    def test_non_git_repo_shows_no_git_message(
        self, mock_validator_cls, tmp_path: Path
    ) -> None:
        mock_result = ValidationResult(
            repo_root=tmp_path,
            health_score=100,
            threshold=0,
            is_git_repo=False,
            passed=True,
        )
        mock_validator_cls.return_value.validate.return_value = mock_result

        runner = CliRunner()
        result = runner.invoke(cli, ["validate", str(tmp_path)])
        assert "not a Git repository" in result.output

    @patch("repomedic.cli.commands.validate.RepositoryValidator")
    def test_scan_error_exits_2(
        self, mock_validator_cls, tmp_path: Path
    ) -> None:
        from repomedic.scanner import ScanError

        mock_validator_cls.return_value.validate.side_effect = ScanError("cannot read")
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", str(tmp_path)])
        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# Helper — set up common pipeline mocks
# ---------------------------------------------------------------------------


def _setup_mocks(
    mock_scanner,
    mock_proj,
    mock_engine,
    mock_git,
    root: Path,
    *,
    issues: list[Issue],
    is_git: bool = False,
    changed: list[str] | None = None,
) -> None:
    """Wire up all pipeline mocks for a validator unit test."""
    from repomedic.scanner.models import ScanResult
    from repomedic.scanner.project_detector import ProjectDetectionResult

    scan_result = ScanResult(root=root, files=[], errors=[])
    mock_scanner.return_value.scan.return_value = scan_result

    proj_result = ProjectDetectionResult()
    mock_proj.return_value.detect.return_value = proj_result

    analysis = AnalysisResult(root=root, issues=issues)
    mock_engine.return_value.run.return_value = analysis

    git_instance = MagicMock()
    git_instance.is_git_repo.return_value = is_git
    git_instance.changed_files.return_value = changed or []
    mock_git.return_value = git_instance
