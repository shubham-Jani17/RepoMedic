"""BlastRadiusAnalyzer — determine which files are affected by a set of changes.

Given a :class:`~repomedic.graph.graph.DependencyGraph` and one or more
changed files, the analyzer performs a reverse-BFS (following dependents, not
dependencies) to discover every downstream file that might be affected.

Usage example::

    from repomedic.graph import build_graph_from_scan, BlastRadiusAnalyzer
    from repomedic.scanner import FileScanner

    scan_result = FileScanner().scan("/path/to/repo")
    graph = build_graph_from_scan(scan_result)

    analyzer = BlastRadiusAnalyzer(graph)
    result = analyzer.analyze(["database.py"])
    print(result.affected_files)   # {"user_service.py", "payment.py", …}
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from repomedic.graph.graph import DependencyGraph, _key


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class BlastRadiusResult:
    """Outcome of a blast-radius analysis run.

    Attributes
    ----------
    changed_files:
        The input set of files reported as changed (normalised to posix strings).
    affected_files:
        All files that transitively depend on at least one changed file.
        Does **not** include the changed files themselves.
    unknown_files:
        Changed files that were not found in the dependency graph.
    cycles_detected:
        Any import cycles found in the graph (list of node-list cycles).
    """

    changed_files: list[str]
    affected_files: set[str] = dataclasses.field(default_factory=set)
    unknown_files: list[str] = dataclasses.field(default_factory=list)
    cycles_detected: list[list[str]] = dataclasses.field(default_factory=list)

    @property
    def total_affected(self) -> int:
        """Number of distinct affected (downstream) files."""
        return len(self.affected_files)

    @property
    def has_impact(self) -> bool:
        """True if at least one downstream file would be affected."""
        return bool(self.affected_files)

    def sorted_affected(self) -> list[str]:
        """Affected files sorted alphabetically for stable output."""
        return sorted(self.affected_files)

    def as_dict(self) -> dict:
        return {
            "changed_files": self.changed_files,
            "affected_files": self.sorted_affected(),
            "total_affected": self.total_affected,
            "unknown_files": self.unknown_files,
            "cycles_detected": self.cycles_detected,
        }


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class BlastRadiusAnalyzer:
    """Compute the blast radius of one or more changed files.

    Parameters
    ----------
    graph:
        A :class:`~repomedic.graph.graph.DependencyGraph` already populated
        with import edges for the repository.
    """

    def __init__(self, graph: DependencyGraph) -> None:
        self._graph = graph

    def analyze(
        self,
        changed: list[str | Path],
    ) -> BlastRadiusResult:
        """Return a :class:`BlastRadiusResult` for the given *changed* files.

        Parameters
        ----------
        changed:
            Repository-relative paths of files that have been modified.
        """
        changed_keys = [_key(f) for f in changed]
        result = BlastRadiusResult(changed_files=changed_keys)

        # Detect cycles once — informational, does not stop analysis
        result.cycles_detected = self._graph.find_cycles()

        # Compute the union of all-dependents for every changed file
        for key in changed_keys:
            if key not in self._graph:
                result.unknown_files.append(key)
                continue
            downstream = self._graph.all_dependents_of(key)
            # Exclude files that are themselves in the changed set
            downstream -= set(changed_keys)
            result.affected_files |= downstream

        return result
