"""Tests for the graph subsystem: ASTParser, DependencyGraph, BlastRadiusAnalyzer."""

from __future__ import annotations

from pathlib import Path

import pytest

from repomedic.graph import (
    ASTParser,
    BlastRadiusAnalyzer,
    BlastRadiusResult,
    DependencyGraph,
    ParseResult,
    build_graph_from_scan,
)
from repomedic.scanner import FileScanner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_py(tmp_path: Path, **files: str) -> Path:
    """Write Python files and return tmp_path."""
    for name, content in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return tmp_path


def scan(path: Path):
    return FileScanner().scan(path)


def build_parser(root: Path, *relative_paths: str) -> ASTParser:
    return ASTParser(
        repo_root=root,
        known_files={Path(p) for p in relative_paths},
    )


# ---------------------------------------------------------------------------
# DependencyGraph — structural
# ---------------------------------------------------------------------------


class TestDependencyGraph:
    def test_add_node(self) -> None:
        g = DependencyGraph()
        g.add_node("a.py")
        assert "a.py" in g
        assert g.dependencies_of("a.py") == set()

    def test_add_edge(self) -> None:
        g = DependencyGraph()
        g.add_edge("a.py", "b.py")
        assert "a.py" in g
        assert "b.py" in g
        assert g.dependencies_of("a.py") == {"b.py"}
        assert g.dependents_of("b.py") == {"a.py"}

    def test_add_edge_creates_nodes(self) -> None:
        g = DependencyGraph()
        g.add_edge("x.py", "y.py")
        assert "x.py" in g
        assert "y.py" in g

    def test_self_loop_ignored(self) -> None:
        g = DependencyGraph()
        g.add_edge("a.py", "a.py")
        assert g.dependencies_of("a.py") == set()

    def test_idempotent_add_edge(self) -> None:
        g = DependencyGraph()
        g.add_edge("a.py", "b.py")
        g.add_edge("a.py", "b.py")
        assert len(g.dependencies_of("a.py")) == 1

    def test_contains_false_for_unknown(self) -> None:
        g = DependencyGraph()
        assert "missing.py" not in g

    def test_nodes(self) -> None:
        g = DependencyGraph()
        g.add_node("a.py")
        g.add_edge("b.py", "c.py")
        assert {"a.py", "b.py", "c.py"} <= g.nodes()

    def test_edge_count(self) -> None:
        g = DependencyGraph()
        g.add_edge("a.py", "b.py")
        g.add_edge("a.py", "c.py")
        assert g.edge_count() == 2

    def test_len(self) -> None:
        g = DependencyGraph()
        g.add_node("a.py")
        g.add_edge("b.py", "c.py")
        assert len(g) == 3


# ---------------------------------------------------------------------------
# DependencyGraph — transitive queries
# ---------------------------------------------------------------------------


class TestDependencyGraphTransitive:
    def _chain_graph(self) -> DependencyGraph:
        """a → b → c → d"""
        g = DependencyGraph()
        g.add_edge("a.py", "b.py")
        g.add_edge("b.py", "c.py")
        g.add_edge("c.py", "d.py")
        return g

    def test_all_dependencies_of_leaf(self) -> None:
        g = self._chain_graph()
        assert g.all_dependencies_of("d.py") == set()

    def test_all_dependencies_of_root(self) -> None:
        g = self._chain_graph()
        assert g.all_dependencies_of("a.py") == {"b.py", "c.py", "d.py"}

    def test_all_dependents_of_root(self) -> None:
        g = self._chain_graph()
        assert g.all_dependents_of("a.py") == set()

    def test_all_dependents_of_leaf(self) -> None:
        g = self._chain_graph()
        assert g.all_dependents_of("d.py") == {"a.py", "b.py", "c.py"}

    def test_all_dependents_of_middle(self) -> None:
        g = self._chain_graph()
        assert g.all_dependents_of("b.py") == {"a.py"}

    def test_all_dependents_multi_parent(self) -> None:
        """Both x.py and y.py import shared.py."""
        g = DependencyGraph()
        g.add_edge("x.py", "shared.py")
        g.add_edge("y.py", "shared.py")
        assert g.all_dependents_of("shared.py") == {"x.py", "y.py"}

    def test_isolated_node_no_deps(self) -> None:
        g = DependencyGraph()
        g.add_node("alone.py")
        assert g.all_dependencies_of("alone.py") == set()
        assert g.all_dependents_of("alone.py") == set()


# ---------------------------------------------------------------------------
# DependencyGraph — cycles
# ---------------------------------------------------------------------------


class TestDependencyGraphCycles:
    def test_no_cycle(self) -> None:
        g = DependencyGraph()
        g.add_edge("a.py", "b.py")
        assert not g.has_cycle()

    def test_simple_cycle(self) -> None:
        g = DependencyGraph()
        g.add_edge("a.py", "b.py")
        g.add_edge("b.py", "a.py")
        assert g.has_cycle()

    def test_three_node_cycle(self) -> None:
        g = DependencyGraph()
        g.add_edge("a.py", "b.py")
        g.add_edge("b.py", "c.py")
        g.add_edge("c.py", "a.py")
        assert g.has_cycle()
        cycles = g.find_cycles()
        assert len(cycles) >= 1

    def test_cycle_traversal_does_not_hang(self) -> None:
        """all_dependents_of must terminate even in a cyclic graph."""
        g = DependencyGraph()
        g.add_edge("a.py", "b.py")
        g.add_edge("b.py", "a.py")
        result = g.all_dependents_of("a.py")
        assert "b.py" in result  # b depends on a (transitively through cycle)

    def test_find_cycles_empty_graph(self) -> None:
        g = DependencyGraph()
        assert g.find_cycles() == []


# ---------------------------------------------------------------------------
# DependencyGraph — topological order
# ---------------------------------------------------------------------------


class TestTopologicalOrder:
    def test_simple_chain(self) -> None:
        """a → b → c  ⟹  order ends with a, b, c from sources to leaves."""
        g = DependencyGraph()
        g.add_edge("a.py", "b.py")
        g.add_edge("b.py", "c.py")
        order = g.topological_order()
        # a must come before b, b before c in dependency direction
        # (sources of imports appear first)
        assert order.index("a.py") < order.index("b.py")
        assert order.index("b.py") < order.index("c.py")

    def test_all_nodes_present(self) -> None:
        g = DependencyGraph()
        g.add_edge("a.py", "b.py")
        g.add_node("c.py")
        order = g.topological_order()
        assert set(order) == {"a.py", "b.py", "c.py"}


# ---------------------------------------------------------------------------
# ASTParser — extraction
# ---------------------------------------------------------------------------


class TestASTParser:
    def test_simple_import(self, tmp_path: Path) -> None:
        make_py(tmp_path, **{
            "main.py": "import utils",
            "utils.py": "pass",
        })
        parser = build_parser(tmp_path, "main.py", "utils.py")
        result = parser.parse_file(Path("main.py"))
        assert Path("utils.py") in result.internal_imports

    def test_from_import(self, tmp_path: Path) -> None:
        make_py(tmp_path, **{
            "main.py": "from helpers import stuff",
            "helpers.py": "def stuff(): pass",
        })
        parser = build_parser(tmp_path, "main.py", "helpers.py")
        result = parser.parse_file(Path("main.py"))
        assert Path("helpers.py") in result.internal_imports

    def test_external_import_not_in_internal(self, tmp_path: Path) -> None:
        make_py(tmp_path, **{"main.py": "import os\nimport sys\nimport requests"})
        parser = build_parser(tmp_path, "main.py")
        result = parser.parse_file(Path("main.py"))
        assert result.internal_imports == []
        assert "os" in result.external_imports

    def test_syntax_error_file_returns_error(self, tmp_path: Path) -> None:
        make_py(tmp_path, **{"bad.py": "def broken(\n    pass"})
        parser = build_parser(tmp_path, "bad.py")
        result = parser.parse_file(Path("bad.py"))
        assert result.errors != []
        assert result.internal_imports == []

    def test_relative_import_same_package(self, tmp_path: Path) -> None:
        make_py(tmp_path, **{
            "pkg/__init__.py": "",
            "pkg/a.py": "from . import b",
            "pkg/b.py": "pass",
        })
        parser = build_parser(
            tmp_path,
            "pkg/__init__.py", "pkg/a.py", "pkg/b.py",
        )
        result = parser.parse_file(Path("pkg/a.py"))
        internal = {p.as_posix() for p in result.internal_imports}
        assert "pkg/b.py" in internal or "pkg/__init__.py" in internal

    def test_relative_import_from_submodule(self, tmp_path: Path) -> None:
        make_py(tmp_path, **{
            "pkg/__init__.py": "",
            "pkg/services.py": "from . import models",
            "pkg/models.py": "pass",
        })
        parser = build_parser(
            tmp_path,
            "pkg/__init__.py", "pkg/services.py", "pkg/models.py",
        )
        result = parser.parse_file(Path("pkg/services.py"))
        internal_posix = {p.as_posix() for p in result.internal_imports}
        assert "pkg/models.py" in internal_posix

    def test_missing_file_returns_error(self, tmp_path: Path) -> None:
        parser = build_parser(tmp_path, "nonexistent.py")
        result = parser.parse_file(Path("nonexistent.py"))
        assert result.errors != []

    def test_parse_files_multiple(self, tmp_path: Path) -> None:
        make_py(tmp_path, **{
            "a.py": "import b",
            "b.py": "import c",
            "c.py": "pass",
        })
        parser = build_parser(tmp_path, "a.py", "b.py", "c.py")
        results = parser.parse_files([Path("a.py"), Path("b.py"), Path("c.py")])
        assert len(results) == 3
        assert isinstance(results[0], ParseResult)

    def test_package_import_resolves(self, tmp_path: Path) -> None:
        make_py(tmp_path, **{
            "app.py": "import mypackage",
            "mypackage/__init__.py": "pass",
        })
        parser = build_parser(tmp_path, "app.py", "mypackage/__init__.py")
        result = parser.parse_file(Path("app.py"))
        internal_posix = {p.as_posix() for p in result.internal_imports}
        assert "mypackage/__init__.py" in internal_posix

    def test_no_imports(self, tmp_path: Path) -> None:
        make_py(tmp_path, **{"pure.py": "x = 1\n"})
        parser = build_parser(tmp_path, "pure.py")
        result = parser.parse_file(Path("pure.py"))
        assert result.internal_imports == []
        assert result.errors == []


# ---------------------------------------------------------------------------
# build_graph_from_scan
# ---------------------------------------------------------------------------


class TestBuildGraphFromScan:
    def test_graph_contains_all_py_files(self, tmp_path: Path) -> None:
        make_py(tmp_path, **{"a.py": "pass", "b.py": "pass", "c.py": "pass"})
        g = build_graph_from_scan(scan(tmp_path))
        assert "a.py" in g
        assert "b.py" in g
        assert "c.py" in g

    def test_import_edge_recorded(self, tmp_path: Path) -> None:
        make_py(tmp_path, **{"main.py": "import utils", "utils.py": "pass"})
        g = build_graph_from_scan(scan(tmp_path))
        assert "utils.py" in g.dependencies_of("main.py")

    def test_parse_errors_collected(self, tmp_path: Path) -> None:
        make_py(tmp_path, **{
            "good.py": "pass",
            "bad.py": "def broken(\n",
        })
        errors: list[str] = []
        g = build_graph_from_scan(scan(tmp_path), errors=errors)
        assert any("bad.py" in e for e in errors)

    def test_non_python_files_excluded(self, tmp_path: Path) -> None:
        make_py(tmp_path, **{"readme.md": "# hi", "app.py": "pass"})
        g = build_graph_from_scan(scan(tmp_path))
        assert "readme.md" not in g


# ---------------------------------------------------------------------------
# BlastRadiusAnalyzer — core scenarios
# ---------------------------------------------------------------------------


class TestBlastRadiusAnalyzer:
    def _linear_graph(self) -> DependencyGraph:
        """database.py ← user_service.py ← payment.py"""
        g = DependencyGraph()
        g.add_edge("user_service.py", "database.py")
        g.add_edge("payment.py", "user_service.py")
        return g

    # --- simple dependency ---
    def test_direct_dependent_included(self) -> None:
        g = self._linear_graph()
        result = BlastRadiusAnalyzer(g).analyze(["database.py"])
        assert "user_service.py" in result.affected_files

    # --- multi-level chain ---
    def test_transitive_dependent_included(self) -> None:
        g = self._linear_graph()
        result = BlastRadiusAnalyzer(g).analyze(["database.py"])
        assert "payment.py" in result.affected_files

    def test_total_affected(self) -> None:
        g = self._linear_graph()
        result = BlastRadiusAnalyzer(g).analyze(["database.py"])
        assert result.total_affected == 2

    # --- no dependents ---
    def test_leaf_no_impact(self) -> None:
        g = self._linear_graph()
        result = BlastRadiusAnalyzer(g).analyze(["payment.py"])
        assert result.affected_files == set()
        assert not result.has_impact
        assert result.total_affected == 0

    # --- multiple changed files ---
    def test_multiple_changed_files(self) -> None:
        g = DependencyGraph()
        g.add_edge("x.py", "lib_a.py")
        g.add_edge("y.py", "lib_b.py")
        result = BlastRadiusAnalyzer(g).analyze(["lib_a.py", "lib_b.py"])
        assert "x.py" in result.affected_files
        assert "y.py" in result.affected_files

    def test_changed_files_excluded_from_affected(self) -> None:
        """A changed file should not appear in its own blast radius."""
        g = self._linear_graph()
        result = BlastRadiusAnalyzer(g).analyze(["database.py", "user_service.py"])
        # user_service.py is both changed AND a dependent of database.py
        # — it must not appear in affected_files
        assert "user_service.py" not in result.affected_files

    # --- unknown / missing files ---
    def test_unknown_file_recorded(self) -> None:
        g = DependencyGraph()
        result = BlastRadiusAnalyzer(g).analyze(["ghost.py"])
        assert "ghost.py" in result.unknown_files
        assert result.affected_files == set()

    # --- circular dependency ---
    def test_circular_dependency_does_not_hang(self) -> None:
        g = DependencyGraph()
        g.add_edge("a.py", "b.py")
        g.add_edge("b.py", "a.py")
        result = BlastRadiusAnalyzer(g).analyze(["a.py"])
        # Should complete and report the cycle
        assert result.cycles_detected != []
        # b.py depends on a (directly), so it should be in affected
        assert "b.py" in result.affected_files

    def test_circular_three_nodes(self) -> None:
        g = DependencyGraph()
        g.add_edge("a.py", "b.py")
        g.add_edge("b.py", "c.py")
        g.add_edge("c.py", "a.py")
        result = BlastRadiusAnalyzer(g).analyze(["a.py"])
        assert result.cycles_detected != []
        assert result.total_affected >= 0  # must not raise

    # --- as_dict ---
    def test_as_dict_structure(self) -> None:
        g = self._linear_graph()
        result = BlastRadiusAnalyzer(g).analyze(["database.py"])
        d = result.as_dict()
        assert set(d.keys()) == {
            "changed_files", "affected_files", "total_affected",
            "unknown_files", "cycles_detected",
        }
        assert d["total_affected"] == 2
        assert isinstance(d["affected_files"], list)

    def test_sorted_affected(self) -> None:
        g = DependencyGraph()
        g.add_edge("z.py", "shared.py")
        g.add_edge("a.py", "shared.py")
        result = BlastRadiusAnalyzer(g).analyze(["shared.py"])
        sorted_list = result.sorted_affected()
        assert sorted_list == sorted(sorted_list)


# ---------------------------------------------------------------------------
# BlastRadiusResult model
# ---------------------------------------------------------------------------


class TestBlastRadiusResult:
    def test_has_impact_true(self) -> None:
        r = BlastRadiusResult(changed_files=["a.py"], affected_files={"b.py"})
        assert r.has_impact

    def test_has_impact_false(self) -> None:
        r = BlastRadiusResult(changed_files=["a.py"])
        assert not r.has_impact

    def test_total_affected_empty(self) -> None:
        r = BlastRadiusResult(changed_files=["a.py"])
        assert r.total_affected == 0


# ---------------------------------------------------------------------------
# Integration: scan → graph → blast radius
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_end_to_end_blast_radius(self, tmp_path: Path) -> None:
        """Full pipeline: write files → scan → build graph → blast radius."""
        make_py(tmp_path, **{
            "database.py": "pass",
            "user_service.py": "import database",
            "payment.py": "import user_service",
            "unrelated.py": "pass",
        })
        g = build_graph_from_scan(scan(tmp_path))
        result = BlastRadiusAnalyzer(g).analyze(["database.py"])

        assert "user_service.py" in result.affected_files
        assert "payment.py" in result.affected_files
        assert "unrelated.py" not in result.affected_files
        assert "database.py" not in result.affected_files

    def test_syntax_error_file_does_not_abort(self, tmp_path: Path) -> None:
        """A file with a syntax error should not abort graph construction."""
        make_py(tmp_path, **{
            "good.py": "pass",
            "bad.py": "def broken(\n",
            "consumer.py": "import good",
        })
        errors: list[str] = []
        g = build_graph_from_scan(scan(tmp_path), errors=errors)
        # 'bad.py' had a parse error — graph still contains other files
        assert "good.py" in g
        assert "consumer.py" in g
        assert any("bad.py" in e for e in errors)

    def test_circular_import_end_to_end(self, tmp_path: Path) -> None:
        make_py(tmp_path, **{
            "a.py": "import b",
            "b.py": "import a",
        })
        g = build_graph_from_scan(scan(tmp_path))
        assert g.has_cycle()
        result = BlastRadiusAnalyzer(g).analyze(["a.py"])
        # Terminates without hanging
        assert isinstance(result.affected_files, set)

    def test_multi_level_chain(self, tmp_path: Path) -> None:
        """a ← b ← c ← d: changing a should affect b, c, d."""
        make_py(tmp_path, **{
            "a.py": "pass",
            "b.py": "import a",
            "c.py": "import b",
            "d.py": "import c",
        })
        g = build_graph_from_scan(scan(tmp_path))
        result = BlastRadiusAnalyzer(g).analyze(["a.py"])
        assert result.affected_files == {"b.py", "c.py", "d.py"}

    def test_diamond_dependency(self, tmp_path: Path) -> None:
        """shared ← left, right ← top: changing shared hits left, right, top."""
        make_py(tmp_path, **{
            "shared.py": "pass",
            "left.py": "import shared",
            "right.py": "import shared",
            "top.py": "import left\nimport right",
        })
        g = build_graph_from_scan(scan(tmp_path))
        result = BlastRadiusAnalyzer(g).analyze(["shared.py"])
        assert "left.py" in result.affected_files
        assert "right.py" in result.affected_files
        assert "top.py" in result.affected_files

    def test_windows_backslash_paths(self) -> None:
        g = DependencyGraph()
        g.add_edge("sub\\a.py", "sub\\b.py")
        assert "sub/a.py" in g
        assert "sub/b.py" in g
        assert g.dependencies_of("sub\\a.py") == {"sub/b.py"}
        assert g.dependents_of("sub\\b.py") == {"sub/a.py"}
        result = BlastRadiusAnalyzer(g).analyze(["sub\\b.py"])
        assert result.affected_files == {"sub/a.py"}
