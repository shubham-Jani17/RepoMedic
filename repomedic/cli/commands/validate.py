"""validate command — repository validation with CI/CD exit codes.

Usage
-----
    repomedic validate <path>
    repomedic validate <path> --fail-under 80

Exit codes
----------
0  PASS — health score ≥ threshold and no blocking errors.
1  FAIL — health score below threshold or blocking errors detected.
2  ERROR — repository could not be scanned.
"""

from __future__ import annotations

import sys

import click

from repomedic.scanner import ScanError
from repomedic.validator import RepositoryValidator, ValidationResult

# ---------------------------------------------------------------------------
# ANSI helpers (duplicated from main to keep this module self-contained)
# ---------------------------------------------------------------------------

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"


def _fmt(text: str, *codes: str) -> str:
    if sys.stdout.isatty():
        return "".join(codes) + text + _RESET
    return text


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_ERROR = 2


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


@click.command("validate")
@click.argument("path", default=".", type=click.Path(file_okay=False))
@click.option(
    "--fail-under",
    "threshold",
    type=click.IntRange(0, 100),
    default=0,
    show_default=True,
    metavar="SCORE",
    help="Minimum acceptable health score (0–100). Fails when score is below this value.",
)
def validate_command(path: str, threshold: int) -> None:
    """Validate that the repository is safe to proceed with.

    PATH is the root directory of the repository.
    Defaults to the current working directory.

    \b
    Examples:
      repomedic validate .
      repomedic validate . --fail-under 80

    Exit codes:
      0  PASS
      1  FAIL (score below threshold or blocking errors)
      2  ERROR (scan failed)
    """
    validator = RepositoryValidator(threshold=threshold)

    try:
        result = validator.validate(path)
    except ScanError as exc:
        click.echo(_fmt(f"Error: {exc}", _RED), err=True)
        sys.exit(EXIT_ERROR)

    _print_result(result)

    sys.exit(EXIT_PASS if result.passed else EXIT_FAIL)


# ---------------------------------------------------------------------------
# Output rendering
# ---------------------------------------------------------------------------


def _print_result(result: ValidationResult) -> None:
    """Render the validation result to stdout."""
    click.echo()
    click.echo(_fmt("Validation Result", _BOLD))
    click.echo(_fmt("-" * 44, _DIM))
    click.echo(f"  Repository    : {_fmt(str(result.repo_root), _CYAN)}")

    # Health score
    score_colour = _GREEN if result.health_score >= result.threshold else _RED
    click.echo(
        f"  Health Score  : {_fmt(str(result.health_score), score_colour)} / 100"
    )

    # Threshold (only show when > 0)
    if result.threshold > 0:
        click.echo(f"  Threshold     : {result.threshold}")

    # Git / changed files
    click.echo(
        f"  Git Repo      : {'yes' if result.is_git_repo else 'no (not a Git repository)'}"
    )

    if result.changed_files:
        click.echo(f"  Changed Files : {len(result.changed_files)}")
        for f in result.changed_files:
            click.echo(f"    {_fmt(f, _DIM)}")
    else:
        click.echo("  Changed Files : (none)")

    # Blast radius
    if result.affected_files:
        click.echo(f"  Blast Radius  : {_fmt(str(result.blast_radius), _YELLOW)} affected file(s)")
        for f in result.affected_files:
            click.echo(f"    {_fmt(f, _DIM)}")
    else:
        click.echo("  Blast Radius  : 0 affected file(s)")

    # Blocking errors
    if result.blocking_errors:
        click.echo(
            f"  Blocking Errors: {_fmt(str(len(result.blocking_errors)), _RED)}"
        )
        for err in result.blocking_errors:
            click.echo(f"    {_fmt(err, _RED)}")
    else:
        click.echo("  Blocking Errors: none")

    # Final verdict
    click.echo()
    click.echo(_fmt("-" * 44, _DIM))
    verdict = "PASS" if result.passed else "FAIL"
    verdict_colour = _GREEN if result.passed else _RED
    click.echo(f"  Result        : {_fmt(verdict, _BOLD, verdict_colour)}")
    click.echo()
