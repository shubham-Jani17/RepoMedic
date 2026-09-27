"""Unit tests for LanguageDetector and ProjectDetector."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from repomedic.cli.main import cli
from repomedic.scanner import (
    FileScanner,
    LanguageDetectionResult,
    LanguageDetector,
    ProjectDetectionResult,
    ProjectDetector,
)
from repomedic.scanner.language_detector import EXTENSION_LANGUAGE_MAP, LanguageStats
from repomedic.scanner.project_detector import KNOWN_CONFIG_FILES


# ---------------------------------------------------------------------------
# Helpers — build a fake repo with specific files
# ---------------------------------------------------------------------------


def make_files(tmp_path: Path, *relative_names: str) -> Path:
    """Create empty files at the given paths under *tmp_path*."""
    for name in relative_names:
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("")
    return tmp_path


def scan(path: Path):
    """Convenience: scan *path* and return the ScanResult."""
    return FileScanner().scan(path)


# ---------------------------------------------------------------------------
# LanguageDetector — basic detection
# ---------------------------------------------------------------------------


class TestLanguageDetectorBasic:
    def test_detects_python(self, tmp_path: Path) -> None:
        make_files(tmp_path, "app.py", "utils.py", "tests/test_main.py")
        result = LanguageDetector().detect(scan(tmp_path))
        stats = result.by_name("Python")
        assert stats is not None
        assert stats.file_count == 3

    def test_detects_javascript(self, tmp_path: Path) -> None:
        make_files(tmp_path, "index.js", "src/app.js")
        result = LanguageDetector().detect(scan(tmp_path))
        assert result.by_name("JavaScript") is not None
        assert result.by_name("JavaScript").file_count == 2  # type: ignore[union-attr]

    def test_detects_typescript(self, tmp_path: Path) -> None:
        make_files(tmp_path, "app.ts", "types.d.ts")
        result = LanguageDetector().detect(scan(tmp_path))
        assert result.by_name("TypeScript") is not None

    def test_detects_java(self, tmp_path: Path) -> None:
        make_files(tmp_path, "src/Main.java")
        result = LanguageDetector().detect(scan(tmp_path))
        assert result.by_name("Java") is not None

    def test_detects_c(self, tmp_path: Path) -> None:
        make_files(tmp_path, "main.c", "utils.h")
        result = LanguageDetector().detect(scan(tmp_path))
        assert result.by_name("C") is not None
        assert result.by_name("C").file_count == 2  # type: ignore[union-attr]

    def test_detects_cpp(self, tmp_path: Path) -> None:
        make_files(tmp_path, "main.cpp", "utils.hpp")
        result = LanguageDetector().detect(scan(tmp_path))
        assert result.by_name("C++") is not None

    def test_detects_go(self, tmp_path: Path) -> None:
        make_files(tmp_path, "main.go", "server/server.go")
        result = LanguageDetector().detect(scan(tmp_path))
        assert result.by_name("Go") is not None
        assert result.by_name("Go").file_count == 2  # type: ignore[union-attr]

    def test_detects_rust(self, tmp_path: Path) -> None:
        make_files(tmp_path, "src/main.rs", "src/lib.rs")
        result = LanguageDetector().detect(scan(tmp_path))
        assert result.by_name("Rust") is not None

    def test_detects_php(self, tmp_path: Path) -> None:
        make_files(tmp_path, "index.php", "src/Controller.php")
        result = LanguageDetector().detect(scan(tmp_path))
        assert result.by_name("PHP") is not None

    def test_detects_ruby(self, tmp_path: Path) -> None:
        make_files(tmp_path, "lib/app.rb", "spec/app_spec.rb")
        result = LanguageDetector().detect(scan(tmp_path))
        assert result.by_name("Ruby") is not None


# ---------------------------------------------------------------------------
# LanguageDetector — ordering and aggregation
# ---------------------------------------------------------------------------


class TestLanguageDetectorOrdering:
    def test_primary_language_most_files(self, tmp_path: Path) -> None:
        make_files(tmp_path, "a.py", "b.py", "c.py", "main.js")
        result = LanguageDetector().detect(scan(tmp_path))
        assert result.primary_language == "Python"

    def test_sorted_by_file_count_descending(self, tmp_path: Path) -> None:
        make_files(tmp_path, "a.py", "b.py", "main.go")
        result = LanguageDetector().detect(scan(tmp_path))
        counts = [s.file_count for s in result.languages]
        assert counts == sorted(counts, reverse=True)

    def test_empty_repo_returns_empty_result(self, tmp_path: Path) -> None:
        result = LanguageDetector().detect(scan(tmp_path))
        assert result.languages == []
        assert result.primary_language is None

    def test_unknown_extensions_ignored(self, tmp_path: Path) -> None:
        make_files(tmp_path, "file.xyz", "data.abc123")
        result = LanguageDetector().detect(scan(tmp_path))
        assert result.languages == []

    def test_byte_count_accumulated(self, tmp_path: Path) -> None:
        p = tmp_path / "app.py"
        p.write_text("x" * 500)
        result = LanguageDetector().detect(scan(tmp_path))
        stats = result.by_name("Python")
        assert stats is not None
        assert stats.byte_count == 500

    def test_language_names_property(self, tmp_path: Path) -> None:
        make_files(tmp_path, "main.py", "main.go")
        result = LanguageDetector().detect(scan(tmp_path))
        assert "Python" in result.language_names
        assert "Go" in result.language_names

    def test_by_name_case_insensitive(self, tmp_path: Path) -> None:
        make_files(tmp_path, "main.py")
        result = LanguageDetector().detect(scan(tmp_path))
        assert result.by_name("python") is not None
        assert result.by_name("PYTHON") is not None

    def test_by_name_missing_returns_none(self, tmp_path: Path) -> None:
        make_files(tmp_path, "main.py")
        result = LanguageDetector().detect(scan(tmp_path))
        assert result.by_name("Rust") is None

    def test_tsx_counted_as_typescript(self, tmp_path: Path) -> None:
        make_files(tmp_path, "App.tsx", "index.ts")
        result = LanguageDetector().detect(scan(tmp_path))
        stats = result.by_name("TypeScript")
        assert stats is not None
        assert stats.file_count == 2


# ---------------------------------------------------------------------------
# LanguageDetector — custom extension map
# ---------------------------------------------------------------------------


class TestLanguageDetectorCustomMap:
    def test_custom_map_used(self, tmp_path: Path) -> None:
        make_files(tmp_path, "code.myext")
        custom = {".myext": "MyLang"}
        result = LanguageDetector(extension_map=custom).detect(scan(tmp_path))
        assert result.by_name("MyLang") is not None

    def test_custom_map_replaces_defaults(self, tmp_path: Path) -> None:
        # If the custom map has no .py entry, Python files should be ignored
        make_files(tmp_path, "app.py")
        result = LanguageDetector(extension_map={}).detect(scan(tmp_path))
        assert result.languages == []


# ---------------------------------------------------------------------------
# LanguageStats model
# ---------------------------------------------------------------------------


class TestLanguageStats:
    def test_display_name(self) -> None:
        s = LanguageStats(name="Python", file_count=5, byte_count=1000)
        assert s.display_name == "Python"

    def test_frozen(self) -> None:
        s = LanguageStats(name="Go", file_count=1, byte_count=100)
        with pytest.raises((AttributeError, TypeError)):
            s.name = "Rust"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ProjectDetector — config file detection
# ---------------------------------------------------------------------------


class TestProjectDetectorConfigs:
    def test_detects_pyproject_toml(self, tmp_path: Path) -> None:
        make_files(tmp_path, "pyproject.toml", "main.py")
        result = ProjectDetector().detect(scan(tmp_path))
        assert result.has_config("pyproject.toml")
        assert "Python" in result.project_types

    def test_detects_requirements_txt(self, tmp_path: Path) -> None:
        make_files(tmp_path, "requirements.txt")
        result = ProjectDetector().detect(scan(tmp_path))
        assert result.has_config("requirements.txt")

    def test_detects_setup_py(self, tmp_path: Path) -> None:
        make_files(tmp_path, "setup.py")
        result = ProjectDetector().detect(scan(tmp_path))
        assert result.has_config("setup.py")

    def test_detects_package_json(self, tmp_path: Path) -> None:
        make_files(tmp_path, "package.json")
        result = ProjectDetector().detect(scan(tmp_path))
        assert result.has_config("package.json")
        assert "JavaScript/TypeScript" in result.project_types

    def test_detects_tsconfig(self, tmp_path: Path) -> None:
        make_files(tmp_path, "tsconfig.json")
        result = ProjectDetector().detect(scan(tmp_path))
        assert result.has_config("tsconfig.json")
        assert "TypeScript" in result.project_types

    def test_detects_pom_xml(self, tmp_path: Path) -> None:
        make_files(tmp_path, "pom.xml")
        result = ProjectDetector().detect(scan(tmp_path))
        assert result.has_config("pom.xml")
        assert "Java (Maven)" in result.project_types

    def test_detects_build_gradle(self, tmp_path: Path) -> None:
        make_files(tmp_path, "build.gradle")
        result = ProjectDetector().detect(scan(tmp_path))
        assert result.has_config("build.gradle")
        assert "Java (Gradle)" in result.project_types

    def test_detects_go_mod(self, tmp_path: Path) -> None:
        make_files(tmp_path, "go.mod", "main.go")
        result = ProjectDetector().detect(scan(tmp_path))
        assert result.has_config("go.mod")
        assert "Go" in result.project_types

    def test_detects_cargo_toml(self, tmp_path: Path) -> None:
        make_files(tmp_path, "Cargo.toml", "src/main.rs")
        result = ProjectDetector().detect(scan(tmp_path))
        assert result.has_config("Cargo.toml")
        assert "Rust" in result.project_types

    def test_detects_csproj_glob(self, tmp_path: Path) -> None:
        make_files(tmp_path, "MyApp.csproj")
        result = ProjectDetector().detect(scan(tmp_path))
        assert ".NET" in result.project_types

    def test_empty_repo_no_configs(self, tmp_path: Path) -> None:
        result = ProjectDetector().detect(scan(tmp_path))
        assert result.detected_configs == []
        assert result.project_types == []

    def test_multiple_project_types_polyglot(self, tmp_path: Path) -> None:
        make_files(tmp_path, "pyproject.toml", "package.json", "go.mod")
        result = ProjectDetector().detect(scan(tmp_path))
        assert "Python" in result.project_types
        assert "JavaScript/TypeScript" in result.project_types
        assert "Go" in result.project_types

    def test_nested_config_found(self, tmp_path: Path) -> None:
        make_files(tmp_path, "backend/requirements.txt", "frontend/package.json")
        result = ProjectDetector().detect(scan(tmp_path))
        assert result.has_config("requirements.txt")
        assert result.has_config("package.json")

    def test_relative_path_recorded(self, tmp_path: Path) -> None:
        make_files(tmp_path, "backend/pyproject.toml")
        result = ProjectDetector().detect(scan(tmp_path))
        assert result.has_config("pyproject.toml")
        cfg = next(d for d in result.detected_configs if d.spec.filename == "pyproject.toml")
        assert "backend" in str(cfg.relative_path)

    def test_ecosystems_deduplicated(self, tmp_path: Path) -> None:
        make_files(tmp_path, "pyproject.toml", "requirements.txt", "setup.py")
        result = ProjectDetector().detect(scan(tmp_path))
        assert result.ecosystems.count("Python") == 1


# ---------------------------------------------------------------------------
# ProjectDetector — standard files
# ---------------------------------------------------------------------------


class TestProjectDetectorStandardFiles:
    def test_readme_present(self, tmp_path: Path) -> None:
        make_files(tmp_path, "README.md")
        result = ProjectDetector().detect(scan(tmp_path))
        assert "README.md" in result.present_standard_files
        assert "README.md" not in result.absent_standard_files

    def test_readme_absent(self, tmp_path: Path) -> None:
        make_files(tmp_path, "main.py")
        result = ProjectDetector().detect(scan(tmp_path))
        assert "README.md" not in result.present_standard_files
        assert "README.md" in result.absent_standard_files

    def test_license_present(self, tmp_path: Path) -> None:
        make_files(tmp_path, "LICENSE")
        result = ProjectDetector().detect(scan(tmp_path))
        assert "LICENSE" in result.present_standard_files

    def test_gitignore_present(self, tmp_path: Path) -> None:
        make_files(tmp_path, ".gitignore")
        result = ProjectDetector().detect(scan(tmp_path))
        assert ".gitignore" in result.present_standard_files

    def test_all_standard_files_tracked(self, tmp_path: Path) -> None:
        make_files(tmp_path, "README.md", "LICENSE", ".gitignore")
        result = ProjectDetector().detect(scan(tmp_path))
        # The three files we created must all be present
        for fname in ("README.md", "LICENSE", ".gitignore"):
            assert fname in result.present_standard_files
            assert fname not in result.absent_standard_files

    def test_no_standard_files(self, tmp_path: Path) -> None:
        # No standard files at all
        result = ProjectDetector().detect(scan(tmp_path))
        assert result.present_standard_files == []


# ---------------------------------------------------------------------------
# Full-stack: multiple repo shapes
# ---------------------------------------------------------------------------


class TestFullRepoShapes:
    def test_pure_python_repo(self, tmp_path: Path) -> None:
        make_files(
            tmp_path,
            "pyproject.toml",
            "README.md",
            ".gitignore",
            "src/app.py",
            "src/utils.py",
            "tests/test_app.py",
        )
        sr = scan(tmp_path)
        lang = LanguageDetector().detect(sr)
        proj = ProjectDetector().detect(sr)

        assert lang.primary_language == "Python"
        assert "Python" in proj.project_types
        assert "README.md" in proj.present_standard_files
        assert ".gitignore" in proj.present_standard_files

    def test_node_ts_repo(self, tmp_path: Path) -> None:
        make_files(
            tmp_path,
            "package.json",
            "tsconfig.json",
            "src/index.ts",
            "src/server.ts",
            "README.md",
        )
        sr = scan(tmp_path)
        lang = LanguageDetector().detect(sr)
        proj = ProjectDetector().detect(sr)

        # package.json + tsconfig.json are counted as JSON, which may rank above
        # TypeScript (.ts) depending on file counts — just assert both are detected
        assert "TypeScript" in lang.language_names
        assert "JSON" in lang.language_names
        assert "JavaScript/TypeScript" in proj.project_types
        assert "TypeScript" in proj.project_types

    def test_go_repo(self, tmp_path: Path) -> None:
        make_files(
            tmp_path,
            "go.mod",
            "main.go",
            "internal/server.go",
            "README.md",
        )
        sr = scan(tmp_path)
        lang = LanguageDetector().detect(sr)
        proj = ProjectDetector().detect(sr)

        assert lang.primary_language == "Go"
        assert "Go" in proj.project_types

    def test_rust_repo(self, tmp_path: Path) -> None:
        make_files(
            tmp_path,
            "Cargo.toml",
            "Cargo.lock",
            "src/main.rs",
            "src/lib.rs",
        )
        sr = scan(tmp_path)
        lang = LanguageDetector().detect(sr)
        proj = ProjectDetector().detect(sr)

        assert lang.primary_language == "Rust"
        assert "Rust" in proj.project_types

    def test_java_maven_repo(self, tmp_path: Path) -> None:
        make_files(
            tmp_path,
            "pom.xml",
            "src/main/java/App.java",
            "src/test/java/AppTest.java",
        )
        sr = scan(tmp_path)
        lang = LanguageDetector().detect(sr)
        proj = ProjectDetector().detect(sr)

        assert lang.primary_language == "Java"
        assert "Java (Maven)" in proj.project_types

    def test_polyglot_repo(self, tmp_path: Path) -> None:
        """A repo mixing Python backend and JS frontend."""
        make_files(
            tmp_path,
            "README.md",
            ".gitignore",
            # backend
            "backend/pyproject.toml",
            "backend/app.py",
            "backend/models.py",
            # frontend
            "frontend/package.json",
            "frontend/tsconfig.json",
            "frontend/src/index.ts",
        )
        sr = scan(tmp_path)
        lang = LanguageDetector().detect(sr)
        proj = ProjectDetector().detect(sr)

        names = lang.language_names
        assert "Python" in names
        assert "TypeScript" in names
        assert "Python" in proj.project_types
        assert "JavaScript/TypeScript" in proj.project_types


# ---------------------------------------------------------------------------
# CLI integration — scan with detection output
# ---------------------------------------------------------------------------


class TestScanCLIWithDetection:
    def test_json_output_has_languages(self, tmp_path: Path) -> None:
        make_files(tmp_path, "app.py", "utils.py")
        runner = CliRunner()
        result = runner.invoke(cli, ["scan", "--format", "json", str(tmp_path)])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert "languages" in payload
        lang_names = [l["name"] for l in payload["languages"]]
        assert "Python" in lang_names

    def test_json_output_has_project_types(self, tmp_path: Path) -> None:
        make_files(tmp_path, "pyproject.toml", "app.py")
        runner = CliRunner()
        result = runner.invoke(cli, ["scan", "--format", "json", str(tmp_path)])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert "project_types" in payload
        assert "Python" in payload["project_types"]

    def test_json_output_has_detected_configs(self, tmp_path: Path) -> None:
        make_files(tmp_path, "go.mod", "main.go")
        runner = CliRunner()
        result = runner.invoke(cli, ["scan", "--format", "json", str(tmp_path)])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert any(c["filename"] == "go.mod" for c in payload["detected_configs"])

    def test_json_output_has_standard_files(self, tmp_path: Path) -> None:
        make_files(tmp_path, "README.md")
        runner = CliRunner()
        result = runner.invoke(cli, ["scan", "--format", "json", str(tmp_path)])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert "present_standard_files" in payload
        assert "absent_standard_files" in payload
        assert "README.md" in payload["present_standard_files"]

    def test_text_output_shows_languages(self, tmp_path: Path) -> None:
        make_files(tmp_path, "app.py", "utils.py")
        runner = CliRunner()
        result = runner.invoke(cli, ["scan", str(tmp_path)])
        assert result.exit_code == 0
        assert "Python" in result.output

    def test_text_output_shows_project_type(self, tmp_path: Path) -> None:
        make_files(tmp_path, "Cargo.toml", "src/main.rs")
        runner = CliRunner()
        result = runner.invoke(cli, ["scan", str(tmp_path)])
        assert result.exit_code == 0
        assert "Rust" in result.output

    def test_text_output_shows_standard_files(self, tmp_path: Path) -> None:
        make_files(tmp_path, "README.md")
        runner = CliRunner()
        result = runner.invoke(cli, ["scan", str(tmp_path)])
        assert result.exit_code == 0
        assert "README.md" in result.output

    def test_text_output_missing_files_flagged(self, tmp_path: Path) -> None:
        make_files(tmp_path, "main.py")
        runner = CliRunner()
        result = runner.invoke(cli, ["scan", str(tmp_path)])
        assert result.exit_code == 0
        assert "missing" in result.output
