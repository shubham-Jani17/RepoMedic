"""ASTParser — extract import relationships from Python source files.

The parser uses Python's stdlib ``ast`` module to walk the parsed tree and
collect every ``import`` and ``from … import`` statement.  Each raw import
specifier is then resolved (best-effort) into a repository-relative path so
that the result can be used to build a :class:`~repomedic.graph.graph.DependencyGraph`.

Resolution strategy
-------------------
1. **Relative imports** (``from . import foo``, ``from ..utils import bar``)
   are resolved using the importing file's location within the package tree.
2. **Absolute imports** are matched against the set of known Python files in
   the repository.  If the dotted module name corresponds to a file or package
   ``__init__.py`` that exists in the repo, we record an edge.
3. **External / stdlib imports** (e.g. ``import os``, ``import requests``)
   that cannot be matched to any file in the repository are silently ignored —
   they are recorded in ``ParseResult.external_imports`` for reference only.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path, PurePosixPath


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class ParseResult:
    """Import relationships extracted from a single Python file."""

    source_file: Path
    """Repository-relative path of the parsed file."""

    internal_imports: list[Path] = dataclasses.field(default_factory=list)
    """Repository-relative paths of project files that this file imports."""

    external_imports: list[str] = dataclasses.field(default_factory=list)
    """Raw module specifiers that could not be resolved to a project file."""

    errors: list[str] = dataclasses.field(default_factory=list)
    """Non-fatal problems encountered while parsing (syntax errors, etc.)."""


# ---------------------------------------------------------------------------
# ASTParser
# ---------------------------------------------------------------------------


class ASTParser:
    """Parse Python files and resolve imports to project-relative paths.

    Parameters
    ----------
    repo_root:
        Absolute path to the repository root.  Used when reading files from
        disk and when resolving absolute import paths.
    known_files:
        Set of *repository-relative* paths for every Python file in the repo.
        Used to determine whether an import resolves to a project file or an
        external dependency.
    """

    def __init__(self, repo_root: Path, known_files: set[Path]) -> None:
        self._root = repo_root
        # Normalise all known files to forward-slash strings for easy lookup
        self._known: set[str] = {_to_posix(p) for p in known_files}
        # Pre-build dotted-module → file mapping for fast absolute-import lookup
        self._module_map: dict[str, str] = self._build_module_map(known_files)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse_file(self, relative_path: Path) -> ParseResult:
        """Parse *relative_path* (relative to the repo root) and return imports.

        Never raises — any problem is recorded in :attr:`ParseResult.errors`.
        """
        result = ParseResult(source_file=relative_path)
        absolute = self._root / relative_path

        # Read source
        try:
            source = absolute.read_text(encoding="utf-8", errors="replace")
        except (PermissionError, OSError) as exc:
            result.errors.append(f"Cannot read {relative_path}: {exc}")
            return result

        # Parse AST
        try:
            tree = ast.parse(source, filename=str(relative_path))
        except SyntaxError as exc:
            result.errors.append(
                f"Syntax error in {relative_path}:{exc.lineno}: {exc.msg}"
            )
            return result

        # Walk imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._resolve_absolute(alias.name, result)

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                level = node.level  # 0 = absolute, 1 = ".", 2 = "..", …

                if level > 0:
                    # Always try the module itself (e.g. `from .utils import x`)
                    self._resolve_relative(module, level, relative_path, result)
                    # Also try each alias as a sibling module
                    # e.g. `from . import b, c` → try pkg/b.py, pkg/c.py
                    if not module:
                        for alias in node.names:
                            self._resolve_relative(alias.name, level, relative_path, result)
                else:
                    self._resolve_absolute(module, result)

        return result

    def parse_files(self, relative_paths: list[Path]) -> list[ParseResult]:
        """Parse multiple files and return a list of :class:`ParseResult`."""
        return [self.parse_file(p) for p in relative_paths]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_absolute(self, module: str, result: ParseResult) -> None:
        """Attempt to resolve an absolute module name to a project file."""
        if not module:
            return
        resolved = self._module_map.get(module)
        if resolved:
            result.internal_imports.append(Path(resolved))
        else:
            result.external_imports.append(module)

    def _resolve_relative(
        self,
        module: str,
        level: int,
        source: Path,
        result: ParseResult,
    ) -> None:
        """Resolve a relative import to a project file."""
        # Compute the package directory for the importing file.
        # level=1 → same package, level=2 → parent package, …
        parts = list(source.parent.parts)
        go_up = level - 1
        if go_up > 0:
            parts = parts[:-go_up] if go_up < len(parts) else []
        base = "/".join(parts) if parts else ""

        if module:
            candidate_module = f"{base}/{module.replace('.', '/')}" if base else module.replace(".", "/")
        else:
            candidate_module = base

        # Try as a direct .py file first, then as a package __init__.py
        for candidate in (
            f"{candidate_module}.py",
            f"{candidate_module}/__init__.py",
        ):
            if candidate in self._known:
                result.internal_imports.append(Path(candidate))
                return

        # Not found — treat as external (could be a stub or c extension)
        spec = f"{'.' * level}{module}" if module else "." * level
        result.external_imports.append(spec)

    @staticmethod
    def _build_module_map(known_files: set[Path]) -> dict[str, str]:
        """Map dotted module names to posix-relative paths.

        For ``src/utils/strings.py`` we register:
        - ``src.utils.strings``   → ``src/utils/strings.py``
        - ``utils.strings``       → ``src/utils/strings.py``   (partial)
        - ``strings``             → ``src/utils/strings.py``   (leaf only)

        We also register the ``__init__.py`` variants for package imports.
        """
        module_map: dict[str, str] = {}

        for rel in known_files:
            posix = _to_posix(rel)
            parts = list(PurePosixPath(posix).parts)

            # Strip .py extension from the last component
            if parts and parts[-1].endswith(".py"):
                last = parts[-1][:-3]
                if last == "__init__":
                    # Package import: ``pkg`` → ``pkg/__init__.py``
                    parts = parts[:-1]
                else:
                    parts[-1] = last
            else:
                continue  # non-py file, skip

            # Register all suffixes of the dotted path to handle both
            # top-level and sub-package imports
            for start in range(len(parts)):
                key = ".".join(parts[start:])
                if key and key not in module_map:
                    module_map[key] = posix

        return module_map


def _to_posix(p: Path | str) -> str:
    """Normalise a Path or str to a forward-slash string."""
    if isinstance(p, Path):
        return p.as_posix()
    return str(p).replace("\\", "/")
