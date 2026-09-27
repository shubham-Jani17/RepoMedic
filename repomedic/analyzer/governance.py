"""GovernanceAnalyzer — detect missing standard repository health files."""

from __future__ import annotations

from repomedic.analyzer.models import AnalysisResult, Category, Issue, Severity
from repomedic.scanner.models import ScanResult
from repomedic.scanner.project_detector import ProjectDetectionResult

# Each entry: (canonical_filename, alternates, severity, title, description, recommendation)
_GOVERNANCE_CHECKS: list[tuple[list[str], Severity, str, str, str]] = [
    (
        ["README.md", "README.rst", "README.txt", "README"],
        Severity.MEDIUM,
        "Missing README",
        (
            "No README file was found in this repository. A README is the first "
            "thing people read when they encounter a project."
        ),
        (
            "Add a README.md at the repository root describing the project purpose, "
            "how to install it, and how to use it."
        ),
    ),
    (
        ["LICENSE", "LICENSE.txt", "LICENSE.md", "LICENCE", "LICENCE.txt"],
        Severity.HIGH,
        "Missing LICENSE",
        (
            "No LICENSE file was found. Without an explicit license, the code is "
            "technically 'all rights reserved' and cannot be legally used, modified, "
            "or distributed by others."
        ),
        (
            "Add a LICENSE file at the repository root. "
            "Choose an OSI-approved license (e.g. MIT, Apache-2.0) at https://choosealicense.com."
        ),
    ),
    (
        [".gitignore"],
        Severity.LOW,
        "Missing .gitignore",
        (
            "No .gitignore file was found. Without it, build artifacts, virtual "
            "environments, and sensitive files may accidentally be committed."
        ),
        (
            "Add a .gitignore at the repository root. "
            "Use https://gitignore.io to generate one for your language/framework."
        ),
    ),
]


class GovernanceAnalyzer:
    """Check for missing standard repository health files."""

    name: str = "GovernanceAnalyzer"

    def analyze(
        self,
        scan_result: ScanResult,
        project_result: ProjectDetectionResult,
        result: AnalysisResult,
    ) -> None:
        # Build a set of all filenames present anywhere in the repo
        present: set[str] = {entry.filename for entry in scan_result.files}

        for alternatives, severity, title, description, recommendation in _GOVERNANCE_CHECKS:
            found = any(name in present for name in alternatives)
            if not found:
                result.issues.append(
                    Issue(
                        title=title,
                        severity=severity,
                        category=Category.GOVERNANCE,
                        description=description,
                        recommendation=recommendation,
                        file=None,
                        line=None,
                    )
                )
