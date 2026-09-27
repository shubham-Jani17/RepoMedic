"""SyntaxAnalyzer — detect syntax errors in Python source files."""

from __future__ import annotations

import ast
import tokenize
from io import StringIO
from pathlib import Path

from repomedic.analyzer.models import AnalysisResult, Category, Issue, Severity
from repomedic.scanner.models import ScanResult
from repomedic.scanner.project_detector import ProjectDetectionResult


class SyntaxAnalyzer:
    """Detect syntax errors in Python source files using the stdlib ``ast`` parser.

    The analyzer reads only ``.py`` files already enumerated by the scanner.
    Files that cannot be decoded as UTF-8 are treated as a warning rather than
    a hard error.
    """

    name: str = "SyntaxAnalyzer"

    def analyze(
        self,
        scan_result: ScanResult,
        project_result: ProjectDetectionResult,
        result: AnalysisResult,
    ) -> None:
        python_files = [f for f in scan_result.files if f.extension == ".py"]
        for entry in python_files:
            self._check_file(entry.absolute_path, entry.relative_path, result)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_file(
        absolute: Path,
        relative: Path,
        result: AnalysisResult,
    ) -> None:
        try:
            source = absolute.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            result.warnings.append(
                f"SyntaxAnalyzer: could not read {relative} as UTF-8 — skipped"
            )
            return
        except PermissionError as exc:
            result.errors.append(f"SyntaxAnalyzer: permission denied reading {relative}: {exc}")
            return
        except OSError as exc:
            result.errors.append(f"SyntaxAnalyzer: OS error reading {relative}: {exc}")
            return

        # --- AST parse: catches most syntax errors ---
        try:
            ast.parse(source, filename=str(relative))
        except SyntaxError as exc:
            result.issues.append(
                Issue(
                    title="Python syntax error",
                    severity=Severity.CRITICAL,
                    category=Category.SYNTAX,
                    description=(
                        f"Python cannot parse this file: {exc.msg}"
                        + (f" (offset {exc.offset})" if exc.offset else "")
                    ),
                    recommendation=(
                        "Fix the syntax error before running any other checks. "
                        "Run `python -m py_compile <file>` for details."
                    ),
                    file=relative,
                    line=exc.lineno,
                )
            )
            return  # no point doing token-level checks on an unparseable file

        # --- tokenize: catches encoding / indentation edge-cases ---
        try:
            list(tokenize.generate_tokens(StringIO(source).readline))
        except tokenize.TokenError as exc:
            msg, (lineno, _) = exc.args
            result.issues.append(
                Issue(
                    title="Python tokenization error",
                    severity=Severity.HIGH,
                    category=Category.SYNTAX,
                    description=f"Tokenizer error in file: {msg}",
                    recommendation=(
                        "Check for unclosed brackets, parentheses, or string literals."
                    ),
                    file=relative,
                    line=lineno,
                )
            )
        except IndentationError as exc:
            result.issues.append(
                Issue(
                    title="Python indentation error",
                    severity=Severity.CRITICAL,
                    category=Category.SYNTAX,
                    description=f"Indentation error: {exc.msg}",
                    recommendation="Ensure consistent use of spaces (PEP 8 recommends 4 spaces).",
                    file=relative,
                    line=exc.lineno,
                )
            )
