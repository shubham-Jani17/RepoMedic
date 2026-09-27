"""ProjectDetector — identify project types and standard repo files from a ScanResult."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from repomedic.scanner.models import ScanResult


# ---------------------------------------------------------------------------
# Known config-file definitions
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class ConfigFileSpec:
    """Describes a well-known project configuration file."""

    filename: str
    project_type: str
    ecosystem: str  # e.g. "Python", "JavaScript", "Java"
    description: str


#: Ordered list of known project configuration files.
KNOWN_CONFIG_FILES: tuple[ConfigFileSpec, ...] = (
    # Python
    ConfigFileSpec("pyproject.toml", "Python", "Python", "PEP 517/518 project descriptor"),
    ConfigFileSpec("requirements.txt", "Python", "Python", "pip dependency list"),
    ConfigFileSpec("setup.py", "Python", "Python", "setuptools setup script"),
    ConfigFileSpec("setup.cfg", "Python", "Python", "setuptools config"),
    ConfigFileSpec("Pipfile", "Python", "Python", "Pipenv dependency file"),
    ConfigFileSpec("poetry.lock", "Python", "Python", "Poetry lock file"),
    # JavaScript / TypeScript
    ConfigFileSpec("package.json", "JavaScript/TypeScript", "JavaScript", "npm/yarn project manifest"),
    ConfigFileSpec("package-lock.json", "JavaScript/TypeScript", "JavaScript", "npm lock file"),
    ConfigFileSpec("yarn.lock", "JavaScript/TypeScript", "JavaScript", "Yarn lock file"),
    ConfigFileSpec("tsconfig.json", "TypeScript", "TypeScript", "TypeScript compiler config"),
    ConfigFileSpec(".eslintrc.json", "JavaScript/TypeScript", "JavaScript", "ESLint config"),
    ConfigFileSpec(".babelrc", "JavaScript/TypeScript", "JavaScript", "Babel transpiler config"),
    # Java
    ConfigFileSpec("pom.xml", "Java (Maven)", "Java", "Maven project descriptor"),
    ConfigFileSpec("build.gradle", "Java (Gradle)", "Java", "Gradle build script"),
    ConfigFileSpec("build.gradle.kts", "Kotlin (Gradle)", "Kotlin", "Gradle Kotlin build script"),
    ConfigFileSpec("settings.gradle", "Java (Gradle)", "Java", "Gradle settings"),
    # Go
    ConfigFileSpec("go.mod", "Go", "Go", "Go module definition"),
    ConfigFileSpec("go.sum", "Go", "Go", "Go module checksum"),
    # Rust
    ConfigFileSpec("Cargo.toml", "Rust", "Rust", "Cargo package manifest"),
    ConfigFileSpec("Cargo.lock", "Rust", "Rust", "Cargo lock file"),
    # Ruby
    ConfigFileSpec("Gemfile", "Ruby", "Ruby", "Bundler dependency file"),
    ConfigFileSpec("Gemfile.lock", "Ruby", "Ruby", "Bundler lock file"),
    # PHP
    ConfigFileSpec("composer.json", "PHP", "PHP", "Composer project manifest"),
    # .NET / C#
    ConfigFileSpec("*.csproj", ".NET", ".NET", "C# project file"),
    ConfigFileSpec("*.sln", ".NET", ".NET", "Visual Studio solution"),
    # Docker / containers
    ConfigFileSpec("Dockerfile", "Docker", "Docker", "Docker image definition"),
    ConfigFileSpec("docker-compose.yml", "Docker", "Docker", "Docker Compose spec"),
    ConfigFileSpec("docker-compose.yaml", "Docker", "Docker", "Docker Compose spec"),
    # CI / DevOps
    ConfigFileSpec("Makefile", "Make", "Build", "GNU Make build file"),
    ConfigFileSpec("Taskfile.yml", "Taskfile", "Build", "Taskfile task runner"),
)

#: Filenames recognised as glob patterns (prefix "*.")
_GLOB_CONFIGS: tuple[ConfigFileSpec, ...] = tuple(
    s for s in KNOWN_CONFIG_FILES if s.filename.startswith("*")
)
_EXACT_CONFIGS: dict[str, ConfigFileSpec] = {
    s.filename: s for s in KNOWN_CONFIG_FILES if not s.filename.startswith("*")
}

# Standard repo health files
_STANDARD_FILES = ("README.md", "README.rst", "README.txt", "LICENSE", "LICENSE.txt", ".gitignore")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class DetectedConfigFile:
    """A config file found in the repository."""

    spec: ConfigFileSpec
    relative_path: Path  # path relative to the repo root where the file was found


@dataclasses.dataclass
class ProjectDetectionResult:
    """Aggregated project-detection outcome for a repository."""

    detected_configs: list[DetectedConfigFile] = dataclasses.field(default_factory=list)

    #: Standard repo health files that are present (filenames only).
    present_standard_files: list[str] = dataclasses.field(default_factory=list)
    #: Standard repo health files that are absent (filenames only).
    absent_standard_files: list[str] = dataclasses.field(default_factory=list)

    @property
    def project_types(self) -> list[str]:
        """Deduplicated list of detected project types, in discovery order."""
        seen: set[str] = set()
        result: list[str] = []
        for cfg in self.detected_configs:
            pt = cfg.spec.project_type
            if pt not in seen:
                seen.add(pt)
                result.append(pt)
        return result

    @property
    def ecosystems(self) -> list[str]:
        """Deduplicated list of detected ecosystems."""
        seen: set[str] = set()
        result: list[str] = []
        for cfg in self.detected_configs:
            eco = cfg.spec.ecosystem
            if eco not in seen:
                seen.add(eco)
                result.append(eco)
        return result

    def has_config(self, filename: str) -> bool:
        """Return True if a config file with this base *filename* was found."""
        return any(cfg.spec.filename == filename for cfg in self.detected_configs)


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------


class ProjectDetector:
    """Identify project types and standard health files from a scan result.

    The detector operates only on the already-collected :class:`ScanResult` —
    it performs no additional filesystem I/O.
    """

    def detect(self, scan_result: ScanResult) -> ProjectDetectionResult:
        """Return a :class:`ProjectDetectionResult` derived from *scan_result*."""
        result = ProjectDetectionResult()

        # Build a set of (filename_lower, relative_path) for fast lookup
        all_filenames: dict[str, list[Path]] = {}
        for entry in scan_result.files:
            key = entry.filename  # preserve original case for glob matching
            all_filenames.setdefault(key, []).append(entry.relative_path)

        # Match exact config filenames
        for filename, spec in _EXACT_CONFIGS.items():
            if filename in all_filenames:
                for rel_path in all_filenames[filename]:
                    result.detected_configs.append(DetectedConfigFile(spec=spec, relative_path=rel_path))

        # Match glob patterns (e.g. "*.csproj")
        for spec in _GLOB_CONFIGS:
            suffix = spec.filename[1:]  # strip leading "*"
            for fname, paths in all_filenames.items():
                if fname.endswith(suffix):
                    for rel_path in paths:
                        result.detected_configs.append(DetectedConfigFile(spec=spec, relative_path=rel_path))

        # Standard health files
        for std_name in _STANDARD_FILES:
            found = any(
                entry.filename == std_name
                for entry in scan_result.files
            )
            if found:
                result.present_standard_files.append(std_name)
            else:
                result.absent_standard_files.append(std_name)

        # Sort detected_configs by relative_path for deterministic output
        result.detected_configs.sort(key=lambda d: str(d.relative_path))

        return result
