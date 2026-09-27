"""Factory helpers — build a DependencyGraph from a ScanResult."""

from __future__ import annotations

from pathlib import Path

from repomedic.graph.ast_parser import ASTParser
from repomedic.graph.graph import DependencyGraph
from repomedic.scanner.models import ScanResult


def build_graph_from_scan(
    scan_result: ScanResult,
    *,
    errors: list[str] | None = None,
) -> DependencyGraph:
    """Parse all Python files in *scan_result* and return a populated graph.

    Parameters
    ----------
    scan_result:
        Output of :class:`~repomedic.scanner.FileScanner`.
    errors:
        If provided, any parse errors encountered are appended here instead
        of being silently discarded.

    Returns
    -------
    DependencyGraph
        Directed graph where an edge A → B means file A imports file B.
    """
    python_files = {f.relative_path for f in scan_result.files if f.extension == ".py"}
    parser = ASTParser(repo_root=scan_result.root, known_files=python_files)
    graph = DependencyGraph()

    for rel_path in python_files:
        graph.add_node(rel_path)

    for rel_path in python_files:
        parse_result = parser.parse_file(rel_path)
        if errors is not None:
            errors.extend(parse_result.errors)
        for dep in parse_result.internal_imports:
            graph.add_edge(rel_path, dep)

    return graph
