"""Tests for the RepoMedic CLI entry point."""

from click.testing import CliRunner

from repomedic.cli.main import cli
from repomedic import __version__


def test_cli_loads() -> None:
    """The CLI group must be importable and invocable without errors."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0


def test_help_output_contains_commands() -> None:
    """--help must list every planned sub-command."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    output = result.output
    for command in ("scan", "analyze", "explain", "fix", "report", "validate"):
        assert command in output, f"Expected '{command}' in --help output"


def test_version_flag() -> None:
    """--version must print the current package version."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_scan_stub(tmp_path) -> None:
    """scan command must run without error on a valid directory."""
    runner = CliRunner()
    result = runner.invoke(cli, ["scan", str(tmp_path)])
    assert result.exit_code == 0
    assert "scan" in result.output.lower()


def test_analyze_stub(tmp_path) -> None:
    """analyze command must run without error on a valid directory."""
    runner = CliRunner()
    result = runner.invoke(cli, ["analyze", str(tmp_path)])
    assert result.exit_code == 0


def test_fix_suggest_mode(tmp_path) -> None:
    """fix --suggest must run without error and show suggestion output."""
    runner = CliRunner()
    result = runner.invoke(cli, ["fix", "--suggest", str(tmp_path)])
    assert result.exit_code == 0
    # Suggest mode must not write any files
    assert not (tmp_path / ".gitignore").exists()


def test_report_stub(tmp_path) -> None:
    """report command must run without error on a valid directory."""
    runner = CliRunner()
    result = runner.invoke(cli, ["report", str(tmp_path)])
    assert result.exit_code == 0


def test_validate_stub(tmp_path) -> None:
    """validate command must run without error on a valid directory."""
    runner = CliRunner()
    result = runner.invoke(cli, ["validate", str(tmp_path)])
    assert result.exit_code == 0


def test_explain_stub_no_id() -> None:
    """explain with no argument must still exit cleanly."""
    runner = CliRunner()
    result = runner.invoke(cli, ["explain"])
    assert result.exit_code == 0
