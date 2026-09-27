"""DependencyGraph — directed dependency graph for a repository.

Nodes are repository-relative file paths (as strings).
An edge  A → B  means "A imports B" (A depends on B).

The graph is stored as two adjacency sets per node:
- ``_deps[A]``  = set of files that A directly imports  (A → *)
- ``_rdeps[B]`` = set of files that directly import B   (* → B)

This dual representation makes both "what does A depend on?" and
"what depends on B?" O(degree) queries without a full graph traversal.
"""

from __future__ import annotations

import dataclasses
from collections import deque
from pathlib import Path
from typing import Iterator


class DependencyGraph:
    """Directed dependency graph where an edge A → B means A imports B.

    All nodes are represented as posix-string paths (e.g. ``"src/app.py"``).
    The class is intentionally framework-free and has no external dependencies.
    """

    def __init__(self) -> None:
        # forward edges:  node → set of its direct dependencies
        self._deps: dict[str, set[str]] = {}
        # reverse edges:  node → set of nodes that depend on it
        self._rdeps: dict[str, set[str]] = {}

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add_node(self, node: str | Path) -> None:
        """Ensure *node* exists in the graph (idempotent)."""
        key = _key(node)
        self._deps.setdefault(key, set())
        self._rdeps.setdefault(key, set())

    def add_edge(self, source: str | Path, target: str | Path) -> None:
        """Add a dependency edge: *source* imports *target*.

        Both nodes are created if they do not already exist.
        Self-loops are silently ignored.
        """
        s, t = _key(source), _key(target)
        if s == t:
            return
        self.add_node(s)
        self.add_node(t)
        self._deps[s].add(t)
        self._rdeps[t].add(s)

    # ------------------------------------------------------------------
    # Queries — direct neighbours
    # ------------------------------------------------------------------

    def dependencies_of(self, node: str | Path) -> set[str]:
        """Return the set of files that *node* directly imports."""
        return set(self._deps.get(_key(node), set()))

    def dependents_of(self, node: str | Path) -> set[str]:
        """Return the set of files that directly import *node*."""
        return set(self._rdeps.get(_key(node), set()))

    def __contains__(self, node: object) -> bool:
        if isinstance(node, (str, Path)):
            return _key(node) in self._deps
        return False

    def nodes(self) -> set[str]:
        """Return all nodes."""
        return set(self._deps.keys())

    def edge_count(self) -> int:
        """Return the total number of directed edges."""
        return sum(len(v) for v in self._deps.values())

    # ------------------------------------------------------------------
    # Queries — transitive reachability
    # ------------------------------------------------------------------

    def all_dependencies_of(self, node: str | Path) -> set[str]:
        """Return *all* transitive dependencies of *node* (BFS, cycle-safe).

        The result does **not** include *node* itself.
        """
        return self._bfs(_key(node), forward=True)

    def all_dependents_of(self, node: str | Path) -> set[str]:
        """Return *all* files that transitively depend on *node* (BFS, cycle-safe).

        This is the "blast radius" of a single changed file.
        The result does **not** include *node* itself.
        """
        return self._bfs(_key(node), forward=False)

    def has_cycle(self) -> bool:
        """Return True if the graph contains at least one cycle."""
        return bool(self.find_cycles())

    def find_cycles(self) -> list[list[str]]:
        """Return a list of cycles found via DFS.

        Each cycle is represented as a list of node strings forming the loop,
        e.g. ``["a.py", "b.py", "a.py"]``.  Only distinct cycles are returned.
        """
        visited: set[str] = set()
        in_stack: set[str] = set()
        stack: list[str] = []
        cycles: list[list[str]] = []

        def dfs(node: str) -> None:
            visited.add(node)
            in_stack.add(node)
            stack.append(node)
            for neighbour in self._deps.get(node, set()):
                if neighbour not in visited:
                    dfs(neighbour)
                elif neighbour in in_stack:
                    # Found a cycle — extract the loop portion
                    idx = stack.index(neighbour)
                    cycle = stack[idx:] + [neighbour]
                    cycles.append(cycle)
            stack.pop()
            in_stack.discard(node)

        for n in list(self._deps):
            if n not in visited:
                dfs(n)

        return cycles

    def topological_order(self) -> list[str]:
        """Return nodes in topological order (dependencies before dependents).

        If the graph contains cycles the cyclic nodes are appended at the end
        in an unspecified order — the caller can detect this by checking
        :meth:`has_cycle` separately.
        """
        in_degree: dict[str, int] = {n: 0 for n in self._deps}
        for deps in self._deps.values():
            for d in deps:
                in_degree[d] = in_degree.get(d, 0) + 1

        queue: deque[str] = deque(n for n, deg in in_degree.items() if deg == 0)
        order: list[str] = []
        while queue:
            node = queue.popleft()
            order.append(node)
            for dep in self._deps.get(node, set()):
                in_degree[dep] -= 1
                if in_degree[dep] == 0:
                    queue.append(dep)

        # Append any remaining nodes (cyclic components)
        remaining = set(self._deps) - set(order)
        order.extend(sorted(remaining))
        return order

    def __iter__(self) -> Iterator[str]:
        return iter(sorted(self._deps))

    def __len__(self) -> int:
        return len(self._deps)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _bfs(self, start: str, *, forward: bool) -> set[str]:
        """BFS from *start* following forward (deps) or reverse (rdeps) edges."""
        adj = self._deps if forward else self._rdeps
        visited: set[str] = set()
        queue: deque[str] = deque(adj.get(start, set()))
        while queue:
            node = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            queue.extend(adj.get(node, set()) - visited)
        return visited


def _key(node: str | Path) -> str:
    """Normalise a node identifier to a forward-slash string."""
    if isinstance(node, Path):
        return node.as_posix()
    return str(node).replace("\\", "/")
