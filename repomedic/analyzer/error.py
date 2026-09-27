"""ErrorAnalyzer — detect obvious error patterns in source files."""

from __future__ import annotations

import re
from pathlib import Path

from repomedic.analyzer.models import AnalysisResult, Category, Issue, Severity
from repomedic.scanner.models import ScanResult
from repomedic.scanner.project_detector import ProjectDetectionResult


# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

# Each entry: (pattern, severity, title, description, recommendation)
# Patterns are applied line-by-line to the relevant file types.
_TODO_PATTERN = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b", re.IGNORECASE)
_DEBUG_PRINT_PATTERN = re.compile(r"^\s*(print\s*\(|console\.log\s*\()", re.MULTILINE)
_PYTHON_BARE_EXCEPT = re.compile(r"^\s*except\s*:", re.MULTILINE)

# File extensions that are plain-text source we want to scan for error patterns
_TEXT_SOURCE_EXTENSIONS = frozenset({
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".java", ".go", ".rs", ".rb", ".php",
    ".c", ".h", ".cpp", ".hpp",
})

# How many TODO/FIXME issues to cap per file (avoid flooding the report)
_MAX_TODOS_PER_FILE = 5


class ErrorAnalyzer:
    """Detect common error-prone patterns in source files.

    Current checks:
    - Bare ``except:`` clauses in Python (swallows all exceptions).
    - TODO / FIXME / HACK / XXX comments (surfaced as INFO).
    - Debug print statements in Python and ``console.log`` in JS/TS.
    """

    name: str = "ErrorAnalyzer"

    def analyze(
        self,
        scan_result: ScanResult,
        project_result: ProjectDetectionResult,
        result: AnalysisResult,
    ) -> None:
        for entry in scan_result.files:
            if entry.extension not in _TEXT_SOURCE_EXTENSIONS:
                continue
            self._check_file(entry.absolute_path, entry.relative_path, result)

    # ------------------------------------------------------------------
    # Per-file analysis
    # ------------------------------------------------------------------

    @staticmethod
    def _check_file(
        absolute: Path,
        relative: Path,
        result: AnalysisResult,
    ) -> None:
        try:
            source = absolute.read_text(encoding="utf-8", errors="replace")
        except (PermissionError, OSError) as exc:
            result.warnings.append(f"ErrorAnalyzer: could not read {relative}: {exc}")
            return

        lines = source.splitlines()
        is_python = relative.suffix.lower() == ".py"
        is_js_ts = relative.suffix.lower() in {".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"}

        todo_count = 0
        for lineno, line in enumerate(lines, start=1):
            # TODO / FIXME / HACK / XXX
            if _TODO_PATTERN.search(line) and todo_count < _MAX_TODOS_PER_FILE:
                match = _TODO_PATTERN.search(line)
                keyword = match.group(0).upper() if match else "TODO"
                result.issues.append(
                    Issue(
                        title=f"{keyword} comment left in source",
                        severity=Severity.INFO,
                        category=Category.ERROR,
                        description=(
                            f"A {keyword} comment was found: "
                            f"{line.strip()[:120]}"
                        ),
                        recommendation=(
                            f"Resolve or track the {keyword} in your issue tracker, "
                            "then remove the comment."
                        ),
                        file=relative,
                        line=lineno,
                    )
                )
                todo_count += 1

            # Bare except: in Python
            if is_python and re.match(r"^\s*except\s*:", line):
                result.issues.append(
                    Issue(
                        title="Bare except clause",
                        severity=Severity.MEDIUM,
                        category=Category.ERROR,
                        description=(
                            "A bare `except:` clause catches all exceptions including "
                            "`SystemExit`, `KeyboardInterrupt`, and `GeneratorExit`. "
                            "This masks bugs and makes debugging very difficult."
                        ),
                        recommendation=(
                            "Catch a specific exception type, e.g. `except ValueError` or "
                            "`except Exception`."
                        ),
                        file=relative,
                        line=lineno,
                    )
                )

            # Debug print statements in Python
            if is_python and re.match(r"^\s*print\s*\(", line):
                result.issues.append(
                    Issue(
                        title="Debug print() statement",
                        severity=Severity.INFO,
                        category=Category.ERROR,
                        description=(
                            "A `print()` statement was found in source code. "
                            "These are often leftover debug statements."
                        ),
                        recommendation=(
                            "Replace with structured logging (`import logging`) or "
                            "remove if no longer needed."
                        ),
                        file=relative,
                        line=lineno,
                    )
                )

            # console.log in JS/TS
            if is_js_ts and re.match(r"^\s*console\.log\s*\(", line):
                result.issues.append(
                    Issue(
                        title="console.log() statement",
                        severity=Severity.INFO,
                        category=Category.ERROR,
                        description=(
                            "A `console.log()` statement was found in source code. "
                            "These are often leftover debug statements."
                        ),
                        recommendation=(
                            "Remove or replace with a proper logging library."
                        ),
                        file=relative,
                        line=lineno,
                    )
                )
