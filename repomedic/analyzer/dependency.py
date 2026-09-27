"""DependencyAnalyzer — foundation-level checks on dependency manifests."""

from __future__ import annotations

from pathlib import Path

from repomedic.analyzer.models import AnalysisResult, Category, Issue, Severity
from repomedic.scanner.models import ScanResult
from repomedic.scanner.project_detector import ProjectDetectionResult


class DependencyAnalyzer:
    """Foundation-level dependency checks.

    Phase 1 checks (implemented here):
    - Detect dependency manifest presence per detected project type.
    - Warn when a lock file is missing alongside a known manifest (e.g.
      ``requirements.txt`` with no ``requirements*.txt`` lock equivalent,
      ``package.json`` with no lock file).

    Deeper dependency graph analysis and vulnerability scanning are deferred
    to later phases.
    """

    name: str = "DependencyAnalyzer"

    def analyze(
        self,
        scan_result: ScanResult,
        project_result: ProjectDetectionResult,
        result: AnalysisResult,
    ) -> None:
        present: set[str] = {entry.filename for entry in scan_result.files}

        self._check_python_lockfile(project_result, present, result)
        self._check_node_lockfile(project_result, present, result)
        self._check_rust_lockfile(project_result, present, result)

    # ------------------------------------------------------------------
    # Per-ecosystem checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_python_lockfile(
        project_result: ProjectDetectionResult,
        present: set[str],
        result: AnalysisResult,
    ) -> None:
        has_pip = project_result.has_config("requirements.txt")
        has_pyproject = project_result.has_config("pyproject.toml")
        has_poetry_lock = "poetry.lock" in present
        has_pipfile_lock = "Pipfile.lock" in present

        # If a plain requirements.txt exists but no lock file, note it as INFO.
        # (requirements.txt *is* effectively a pin file; we just note the pattern.)
        if has_pip and not has_poetry_lock and not has_pipfile_lock:
            result.issues.append(
                Issue(
                    title="Python: using requirements.txt without a lock file",
                    severity=Severity.INFO,
                    category=Category.DEPENDENCY,
                    description=(
                        "The project uses requirements.txt for dependencies but has no "
                        "dedicated lock file (poetry.lock, Pipfile.lock). "
                        "Without a lock file, builds may not be fully reproducible."
                    ),
                    recommendation=(
                        "Consider using pip-tools (`pip-compile`) to generate a "
                        "requirements.txt with pinned hashes, or migrate to Poetry or Pipenv."
                    ),
                )
            )

        # If pyproject.toml present without any lock file, flag it.
        if has_pyproject and not has_poetry_lock and not has_pipfile_lock:
            result.issues.append(
                Issue(
                    title="Python: pyproject.toml without a lock file",
                    severity=Severity.INFO,
                    category=Category.DEPENDENCY,
                    description=(
                        "A pyproject.toml exists but no lock file (poetry.lock) was found. "
                        "Builds may not be reproducible."
                    ),
                    recommendation=(
                        "If using Poetry, run `poetry lock` to generate poetry.lock and commit it. "
                        "If using pip/setuptools, consider pip-tools for pinning."
                    ),
                )
            )

    @staticmethod
    def _check_node_lockfile(
        project_result: ProjectDetectionResult,
        present: set[str],
        result: AnalysisResult,
    ) -> None:
        if not project_result.has_config("package.json"):
            return

        has_npm_lock = "package-lock.json" in present
        has_yarn_lock = "yarn.lock" in present
        has_pnpm_lock = "pnpm-lock.yaml" in present

        if not (has_npm_lock or has_yarn_lock or has_pnpm_lock):
            result.issues.append(
                Issue(
                    title="JavaScript/TypeScript: package.json without a lock file",
                    severity=Severity.MEDIUM,
                    category=Category.DEPENDENCY,
                    description=(
                        "package.json was found but no lock file (package-lock.json, "
                        "yarn.lock, pnpm-lock.yaml) is present. "
                        "Dependency versions are not pinned, leading to non-reproducible installs."
                    ),
                    recommendation=(
                        "Run `npm install`, `yarn install`, or `pnpm install` to generate "
                        "a lock file and commit it to the repository."
                    ),
                )
            )

    @staticmethod
    def _check_rust_lockfile(
        project_result: ProjectDetectionResult,
        present: set[str],
        result: AnalysisResult,
    ) -> None:
        if not project_result.has_config("Cargo.toml"):
            return
        if "Cargo.lock" not in present:
            result.issues.append(
                Issue(
                    title="Rust: Cargo.toml without Cargo.lock",
                    severity=Severity.LOW,
                    category=Category.DEPENDENCY,
                    description=(
                        "Cargo.toml was found but Cargo.lock is absent. "
                        "For binary crates, Cargo.lock should be committed to guarantee "
                        "reproducible builds."
                    ),
                    recommendation=(
                        "Run `cargo build` or `cargo check` to generate Cargo.lock and "
                        "commit it if this is an application (not a library)."
                    ),
                )
            )
