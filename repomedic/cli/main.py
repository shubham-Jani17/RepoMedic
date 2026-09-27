"""RepoMedic CLI — entry point and command group."""

from __future__ import annotations

import json
import sys

import click

from repomedic import __version__
from repomedic.ai import (
    AIProviderError,
    ContextBuilder,
    ProviderNotAvailableError,
    get_analyzer,
)
from repomedic.analyzer import (
    AnalysisEngine,
    AnalysisResult,
    Severity,
    SEVERITY_COLOURS,
    SEVERITY_LABELS,
)
from repomedic.fixer import (
    ApplyReport,
    AutoFixer,
    FixSuggestion,
    FixStatus,
    FixVerifier,
    PatchGenerator,
    VerificationResult,
)
from repomedic.reporter import (
    JSONReporter,
    ReportBuilder,
    TerminalReporter,
)
from repomedic.scanner import (
    FileScanner,
    LanguageDetector,
    ProjectDetector,
    ScanError,
)

# ---------------------------------------------------------------------------
# Formatting helpers (text output)
# ---------------------------------------------------------------------------

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_CYAN = "\033[36m"


def _fmt(text: str, *codes: str) -> str:
    """Apply ANSI codes only when stdout is a real terminal."""
    if sys.stdout.isatty():
        return "".join(codes) + text + _RESET
    return text


@click.group()
@click.version_option(version=__version__, prog_name="repomedic")
def cli() -> None:
    """RepoMedic — repository health analysis and repair tool.

    Analyzes a software repository, identifies problems, explains likely
    root causes, suggests or safely applies fixes, verifies changes,
    calculates a repository health score, analyzes dependency impact, and
    validates whether the repository is safe to proceed with.

    \b
    Quick start:
      repomedic scan        Scan a repository for problems
      repomedic analyze     Analyze and rank identified problems
      repomedic explain     Explain root causes of a problem
      repomedic fix         Suggest or apply fixes
      repomedic report      Generate a health report
      repomedic validate    Validate the repository is safe to proceed
    """


# ---------------------------------------------------------------------------
# Sub-commands (stub implementations — full logic added in later phases)
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("path", default=".", type=click.Path(file_okay=False))
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"], case_sensitive=False),
    default="text",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--top",
    default=10,
    show_default=True,
    help="Number of top file extensions to display.",
)
def scan(path: str, output_format: str, top: int) -> None:
    """Scan a repository for problems.

    PATH is the root directory of the repository to scan.
    Defaults to the current working directory.
    """
    scanner = FileScanner()
    try:
        scan_result = scanner.scan(path)
    except ScanError as exc:
        click.echo(_fmt(f"Error: {exc}", _RED), err=True)
        sys.exit(1)

    lang_result = LanguageDetector().detect(scan_result)
    proj_result = ProjectDetector().detect(scan_result)

    if output_format == "json":
        payload = {
            "root": str(scan_result.root),
            "file_count": scan_result.file_count,
            "total_size_bytes": scan_result.total_size_bytes,
            "extension_counts": scan_result.extension_counts,
            "languages": [
                {"name": s.name, "file_count": s.file_count, "byte_count": s.byte_count}
                for s in lang_result.languages
            ],
            "project_types": proj_result.project_types,
            "ecosystems": proj_result.ecosystems,
            "detected_configs": [
                {
                    "filename": d.spec.filename,
                    "project_type": d.spec.project_type,
                    "description": d.spec.description,
                    "path": str(d.relative_path),
                }
                for d in proj_result.detected_configs
            ],
            "present_standard_files": proj_result.present_standard_files,
            "absent_standard_files": proj_result.absent_standard_files,
            "ignored_dirs": scan_result.ignored_dirs,
            "errors": scan_result.errors,
        }
        click.echo(json.dumps(payload, indent=2))
        return

    # --- text output ---
    click.echo()
    click.echo(_fmt("Repository scan", _BOLD))
    click.echo(_fmt("-" * 40, _DIM))
    click.echo(f"  Path       : {_fmt(str(scan_result.root), _CYAN)}")
    click.echo(f"  Files found: {_fmt(str(scan_result.file_count), _GREEN)}")
    click.echo(f"  Total size : {_human_size(scan_result.total_size_bytes)}")
    click.echo()

    # Languages
    if lang_result.languages:
        click.echo(_fmt("Languages:", _BOLD))
        for stats in lang_result.languages[:top]:
            bar = "#" * min(stats.file_count, 30)
            click.echo(f"  {stats.name:<20} {stats.file_count:>5} files  {_fmt(bar, _CYAN)}")
        click.echo()

    # Project types
    if proj_result.project_types:
        click.echo(_fmt("Project types:", _BOLD))
        for pt in proj_result.project_types:
            click.echo(f"  {_fmt(pt, _GREEN)}")
        click.echo()

    # Detected config files
    if proj_result.detected_configs:
        click.echo(_fmt("Config files found:", _BOLD))
        for detected in proj_result.detected_configs:
            click.echo(
                f"  {detected.spec.filename:<28} {_fmt(str(detected.relative_path), _DIM)}"
            )
        click.echo()

    # Standard health files
    if proj_result.present_standard_files or proj_result.absent_standard_files:
        click.echo(_fmt("Standard files:", _BOLD))
        for fname in proj_result.present_standard_files:
            click.echo(f"  [+] {fname}")
        for fname in proj_result.absent_standard_files:
            click.echo(f"  [-] {_fmt(fname, _DIM)}  (missing)")
        click.echo()

    # Extension breakdown
    ext_counts = scan_result.extension_counts
    if ext_counts:
        click.echo(_fmt(f"Top {min(top, len(ext_counts))} file types (by extension):", _BOLD))
        for ext, count in list(ext_counts.items())[:top]:
            bar = "#" * min(count, 30)
            click.echo(f"  {ext:<18} {count:>5}  {_fmt(bar, _CYAN)}")
        click.echo()

    if scan_result.ignored_dirs:
        click.echo(_fmt(f"Ignored directories ({len(scan_result.ignored_dirs)}):", _BOLD))
        shown = scan_result.ignored_dirs[:8]
        for d in shown:
            click.echo(f"  {_fmt(d, _DIM)}")
        if len(scan_result.ignored_dirs) > 8:
            click.echo(f"  ... and {len(scan_result.ignored_dirs) - 8} more")
        click.echo()

    if scan_result.errors:
        click.echo(_fmt(f"Warnings ({len(scan_result.errors)}):", _RED))
        for err in scan_result.errors:
            click.echo(f"  {err}")
        click.echo()


def _human_size(nbytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024  # type: ignore[assignment]
    return f"{nbytes:.1f} TB"


@cli.command()
@click.argument("path", default=".", type=click.Path(file_okay=False))
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"], case_sensitive=False),
    default="text",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--min-severity",
    type=click.Choice(["info", "low", "medium", "high", "critical"], case_sensitive=False),
    default="info",
    show_default=True,
    help="Only display issues at or above this severity.",
)
def analyze(path: str, output_format: str, min_severity: str) -> None:
    """Analyze a repository and display ranked findings.

    PATH is the root directory of the repository to analyze.
    Defaults to the current working directory.
    """
    # 1. Scan
    scanner = FileScanner()
    try:
        scan_result = scanner.scan(path)
    except ScanError as exc:
        click.echo(_fmt(f"Error: {exc}", _RED), err=True)
        sys.exit(1)

    # 2. Detect project structure
    proj_result = ProjectDetector().detect(scan_result)

    # 3. Run analyzers
    engine = AnalysisEngine()
    analysis = engine.run(scan_result, proj_result)

    # 4. Filter by min severity
    threshold = Severity(min_severity.lower())
    visible = [i for i in analysis.issues if i.severity >= threshold]

    if output_format == "json":
        payload = {
            "root": str(analysis.root),
            "issue_count": len(visible),
            "errors": analysis.errors,
            "warnings": analysis.warnings,
            "severity_counts": analysis.severity_counts(),
            "issues": [i.as_dict() for i in visible],
        }
        click.echo(json.dumps(payload, indent=2))
        return

    # --- text output ---
    _print_analysis(analysis, visible, engine.analyzer_names)


def _print_analysis(
    analysis: AnalysisResult,
    visible: list,
    analyzer_names: list[str],
) -> None:
    """Render analysis results to stdout in human-readable form."""
    RESET = "\033[0m"

    click.echo()
    click.echo(_fmt("Analysis results", _BOLD))
    click.echo(_fmt("-" * 40, _DIM))
    click.echo(f"  Repository : {_fmt(str(analysis.root), _CYAN)}")
    click.echo(f"  Analyzers  : {', '.join(analyzer_names)}")
    click.echo(f"  Issues     : {_fmt(str(len(visible)), _GREEN if not visible else _RED)}")
    click.echo()

    # Severity summary bar
    counts = analysis.severity_counts()
    summary_parts = []
    for sev in Severity:
        n = counts.get(sev.value, 0)
        if n:
            colour = SEVERITY_COLOURS[sev] if sys.stdout.isatty() else ""
            label = sev.value.upper()
            summary_parts.append(f"{colour}{label}: {n}{RESET if sys.stdout.isatty() else ''}")
    if summary_parts:
        click.echo("  " + "  ".join(summary_parts))
        click.echo()

    if not visible:
        click.echo(_fmt("  No issues found at this severity threshold.", _GREEN))
        click.echo()
        return

    # Issue list
    for issue in visible:
        colour = SEVERITY_COLOURS[issue.severity] if sys.stdout.isatty() else ""
        label = SEVERITY_LABELS[issue.severity]
        loc = ""
        if issue.file:
            loc = f"  {_fmt(str(issue.file), _DIM)}"
            if issue.line:
                loc += f":{issue.line}"

        click.echo(
            f"  {colour}{label}{RESET if sys.stdout.isatty() else ''}  "
            f"{_fmt(issue.title, _BOLD)}{loc}"
        )
        click.echo(f"  {'':8}  {issue.description[:140]}")
        click.echo(f"  {'':8}  {_fmt('Recommendation:', _DIM)} {issue.recommendation[:120]}")
        click.echo()

    if analysis.errors:
        click.echo(_fmt(f"Analyzer errors ({len(analysis.errors)}):", _RED))
        for err in analysis.errors:
            click.echo(f"  {err}")
        click.echo()

    if analysis.warnings:
        click.echo(_fmt(f"Warnings ({len(analysis.warnings)}):", _DIM))
        for w in analysis.warnings:
            click.echo(f"  {w}")
        click.echo()


@cli.command()
@click.argument("path", default=".", type=click.Path(file_okay=False))
@click.option(
    "--issue-id",
    default=None,
    help="Focus on a specific issue ID returned by a previous 'analyze' run.",
)
@click.option(
    "--provider",
    default=None,
    help="AI provider to use (e.g. 'openai', 'mock'). Defaults to auto-selection.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"], case_sensitive=False),
    default="text",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--note",
    default="",
    help="Optional free-form note to focus the AI's attention.",
)
def explain(
    path: str,
    issue_id: str | None,
    provider: str | None,
    output_format: str,
    note: str,
) -> None:
    """Explain root causes of problems using AI analysis.

    PATH is the root directory of the repository to analyze.
    Defaults to the current working directory.

    \b
    Examples:
      repomedic explain .
      repomedic explain . --issue-id abc12345
      repomedic explain . --provider openai
    """
    # 1. Scan
    scanner = FileScanner()
    try:
        scan_result = scanner.scan(path)
    except ScanError as exc:
        click.echo(_fmt(f"Error: {exc}", _RED), err=True)
        sys.exit(1)

    # 2. Detect project structure
    proj_result = ProjectDetector().detect(scan_result)

    # 3. Run analyzers
    engine = AnalysisEngine()
    analysis = engine.run(scan_result, proj_result)

    # 4. Build diagnostic context
    context = ContextBuilder(
        scan_result,
        proj_result,
        analysis,
        focus_issue_id=issue_id,
        focus_note=note,
    ).build()

    # 5. Select AI provider
    try:
        analyzer = get_analyzer(provider=provider)
    except (ProviderNotAvailableError, ValueError) as exc:
        click.echo(_fmt(f"Error selecting AI provider: {exc}", _RED), err=True)
        sys.exit(1)

    # 6. Run AI analysis
    try:
        explanation = analyzer.explain(context)
    except AIProviderError as exc:
        click.echo(_fmt(f"AI provider error: {exc}", _RED), err=True)
        sys.exit(1)

    # 7. Output
    if output_format == "json":
        payload = {
            "repo_root": str(scan_result.root),
            "provider": explanation.provider,
            "context_issues": len(context.issues),
            "explanation": explanation.as_dict(),
        }
        click.echo(json.dumps(payload, indent=2))
        return

    _print_explanation(explanation, scan_result.root, analyzer.name, len(context.issues))


def _print_explanation(explanation, repo_root, provider_name: str, issue_count: int) -> None:
    """Render an AIExplanation to stdout in human-readable form."""
    click.echo()
    click.echo(_fmt("AI Explanation", _BOLD))
    click.echo(_fmt("-" * 40, _DIM))
    click.echo(f"  Repository : {_fmt(str(repo_root), _CYAN)}")
    click.echo(f"  Provider   : {_fmt(provider_name, _GREEN)}")
    click.echo(f"  Issues in context: {issue_count}")
    click.echo()

    confidence_colour = {
        "high": _GREEN,
        "medium": _CYAN,
        "low": "\033[33m",  # yellow
    }.get(explanation.confidence, _CYAN)

    click.echo(
        f"  {_fmt('Confidence', _BOLD)}  : "
        f"{_fmt(explanation.confidence.upper(), confidence_colour)}"
    )
    click.echo()

    click.echo(_fmt("  Root cause", _BOLD))
    click.echo(f"  {explanation.root_cause}")
    click.echo()

    click.echo(_fmt("  Explanation", _BOLD))
    for line in _wrap(explanation.explanation, width=78):
        click.echo(f"  {line}")
    click.echo()

    click.echo(_fmt("  Recommended fix", _BOLD))
    for line in _wrap(explanation.recommended_fix, width=78):
        click.echo(f"  {line}")
    click.echo()

    if explanation.affected_components:
        click.echo(_fmt("  Affected components", _BOLD))
        for comp in explanation.affected_components:
            click.echo(f"    {_fmt(comp, _DIM)}")
        click.echo()


def _wrap(text: str, width: int = 78) -> list[str]:
    """Naive word-wrap so long AI responses stay readable in a terminal."""
    import textwrap
    return textwrap.wrap(text, width=width) or [text]


@cli.command()
@click.argument("path", default=".", type=click.Path(file_okay=False))
@click.option(
    "--suggest",
    "mode",
    flag_value="suggest",
    help="Show proposed fixes without modifying the repository.",
)
@click.option(
    "--apply",
    "mode",
    flag_value="apply",
    help="Apply supported safe fixes (governance files only).",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"], case_sensitive=False),
    default="text",
    show_default=True,
    help="Output format.",
)
def fix(path: str, mode: str | None, output_format: str) -> None:
    """Suggest or apply safe fixes for identified problems.

    PATH is the root directory of the repository.
    Defaults to the current working directory.

    \b
    Modes:
      --suggest   Show what would be fixed without writing any files.
      --apply     Create governance files (.gitignore, README.md, LICENSE)
                  and verify that targeted issues are resolved.

    \b
    Safety:
      - Never overwrites existing files.
      - Never deletes files.
      - Never modifies arbitrary source code.
      - Reports every action taken (created / skipped / error).
    """
    if mode is None:
        # Default to suggest so the command is safe to run with no flags
        mode = "suggest"

    # 1. Scan & analyse
    scanner = FileScanner()
    try:
        scan_result = scanner.scan(path)
    except ScanError as exc:
        click.echo(_fmt(f"Error: {exc}", _RED), err=True)
        sys.exit(1)

    proj_result = ProjectDetector().detect(scan_result)
    engine = AnalysisEngine()
    analysis = engine.run(scan_result, proj_result)

    # 2. Generate suggestions (pure — no FS writes)
    generator = PatchGenerator(project_name=scan_result.root.name)
    suggestions, unsupported = generator.generate(analysis)

    if output_format == "json" and mode == "suggest":
        payload = {
            "repo_root": str(scan_result.root),
            "mode": mode,
            "suggestions": [s.as_dict() for s in suggestions],
            "unsupported_count": len(unsupported),
            "unsupported_titles": [i.title for i in unsupported],
        }
        click.echo(json.dumps(payload, indent=2))
        return

    if mode == "suggest":
        _print_suggestions(suggestions, unsupported, scan_result.root)
        return

    # mode == "apply"
    fixer = AutoFixer(scan_result.root)
    report = fixer.apply(suggestions)

    # 3. Verify
    verifier = FixVerifier(scan_result.root)
    verification = verifier.verify(analysis, report)

    if output_format == "json":
        payload = {
            "repo_root": str(scan_result.root),
            "mode": mode,
            "apply_report": report.as_dict(),
            "verification": verification.as_dict(),
        }
        click.echo(json.dumps(payload, indent=2))
        return

    _print_apply_report(report, scan_result.root)
    _print_verification(verification)


def _print_suggestions(
    suggestions: list[FixSuggestion],
    unsupported: list,
    repo_root,
) -> None:
    click.echo()
    click.echo(_fmt("Fix suggestions", _BOLD))
    click.echo(_fmt("-" * 40, _DIM))
    click.echo(f"  Repository : {_fmt(str(repo_root), _CYAN)}")
    click.echo()

    if not suggestions:
        click.echo(_fmt("  No automated fixes available.", _GREEN))
    else:
        click.echo(_fmt(f"  {len(suggestions)} fix(es) available:", _BOLD))
        click.echo()
        for s in suggestions:
            click.echo(
                f"  {_fmt('[create]', _GREEN)}  "
                f"{_fmt(str(s.target_path), _BOLD)}"
            )
            click.echo(f"             {s.rationale}")
            click.echo()

    if unsupported:
        click.echo(_fmt(f"  {len(unsupported)} issue(s) without an automated fix:", _DIM))
        for issue in unsupported:
            click.echo(f"    {_fmt('·', _DIM)} {issue.title}")
        click.echo()

    click.echo(
        _fmt(
            "  Run with --apply to create the suggested files.",
            _DIM,
        )
    )
    click.echo()


def _print_apply_report(report: ApplyReport, repo_root) -> None:
    click.echo()
    click.echo(_fmt("Fix results", _BOLD))
    click.echo(_fmt("-" * 40, _DIM))
    click.echo(f"  Repository : {_fmt(str(repo_root), _CYAN)}")
    click.echo()

    for result in report.results:
        if result.status == FixStatus.CREATED:
            icon = _fmt("[created]", _GREEN)
        elif result.status == FixStatus.SKIPPED:
            icon = _fmt("[skipped]", _DIM)
        else:
            icon = _fmt("[error]  ", _RED)

        click.echo(
            f"  {icon}  "
            f"{_fmt(str(result.suggestion.target_path), _BOLD)}"
            + (f"  - {result.message}" if result.message else "")
        )

    click.echo()
    click.echo(
        f"  Created: {_fmt(str(len(report.created)), _GREEN)}  "
        f"Skipped: {_fmt(str(len(report.skipped)), _DIM)}  "
        f"Errors: {_fmt(str(len(report.errors)), _RED if report.errors else _DIM)}"
    )
    click.echo()


def _print_verification(verification: VerificationResult) -> None:
    if not verification.resolutions:
        return

    click.echo(_fmt("Verification", _BOLD))
    click.echo(_fmt("-" * 40, _DIM))
    click.echo()

    for res in verification.resolutions:
        icon = _fmt("[resolved]  ", _GREEN) if res.resolved else _fmt("[unresolved]", _RED)
        click.echo(f"  {icon}  {res.issue_title}")

    click.echo()

    if verification.all_resolved:
        click.echo(_fmt("  All targeted issues resolved.", _GREEN))
    else:
        click.echo(
            _fmt(
                f"  {verification.unresolved_count} issue(s) still present after fix.",
                _RED,
            )
        )

    if verification.new_issues_count:
        click.echo(
            _fmt(
                f"  Warning: {verification.new_issues_count} new issue(s) appeared.",
                _RED,
            )
        )
    click.echo()


@cli.command()
@click.argument("path", default=".", type=click.Path(file_okay=False))
@click.option(
    "--json",
    "output_format",
    flag_value="json",
    help="Output as machine-readable JSON.",
)
@click.option(
    "--text",
    "output_format",
    flag_value="text",
    default=True,
    help="Output as human-readable text (default).",
)
@click.option(
    "--all-issues",
    is_flag=True,
    default=False,
    help="Show all issues regardless of severity (default: medium and above).",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default=None,
    help="Write report to a file instead of stdout.",
)
def report(
    path: str,
    output_format: str,
    all_issues: bool,
    output: str | None,
) -> None:
    """Generate a repository health report.

    PATH is the root directory of the repository.
    Defaults to the current working directory.

    \b
    Examples:
      repomedic report .
      repomedic report --json .
      repomedic report --json . -o report.json
    """
    # 1. Scan
    scanner = FileScanner()
    try:
        scan_result = scanner.scan(path)
    except ScanError as exc:
        click.echo(_fmt(f"Error: {exc}", _RED), err=True)
        sys.exit(1)

    # 2. Detect
    proj_result = ProjectDetector().detect(scan_result)
    lang_result = LanguageDetector().detect(scan_result)

    # 3. Analyse
    engine = AnalysisEngine()
    analysis = engine.run(scan_result, proj_result)

    # 4. Build report data
    data = ReportBuilder(scan_result, proj_result, lang_result, analysis).build()

    # 5. Open output stream (file or stdout)
    if output:
        try:
            out_file = open(output, "w", encoding="utf-8")
        except OSError as exc:
            click.echo(_fmt(f"Error opening output file: {exc}", _RED), err=True)
            sys.exit(1)
    else:
        out_file = None

    stream = out_file or sys.stdout

    # 6. Render
    try:
        if output_format == "json":
            JSONReporter(stream=stream).render(data)
        else:
            TerminalReporter(stream=stream, show_all_issues=all_issues).render(data)
    finally:
        if out_file:
            out_file.close()


from repomedic.cli.commands.validate import validate_command as validate

cli.add_command(validate)
