"""LanguageDetector — identify programming languages from a ScanResult."""

from __future__ import annotations

import dataclasses
from collections import Counter

from repomedic.scanner.models import FileEntry, ScanResult


# ---------------------------------------------------------------------------
# Extension → language mapping
# ---------------------------------------------------------------------------

#: Map of normalised file extension (with leading dot) to language name.
EXTENSION_LANGUAGE_MAP: dict[str, str] = {
    # Python
    ".py": "Python",
    ".pyi": "Python",
    ".pyw": "Python",
    # JavaScript
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".jsx": "JavaScript",
    # TypeScript
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".mts": "TypeScript",
    ".cts": "TypeScript",
    # Java
    ".java": "Java",
    # C
    ".c": "C",
    ".h": "C",
    # C++
    ".cpp": "C++",
    ".cxx": "C++",
    ".cc": "C++",
    ".hpp": "C++",
    ".hxx": "C++",
    ".hh": "C++",
    # Go
    ".go": "Go",
    # Rust
    ".rs": "Rust",
    # PHP
    ".php": "PHP",
    ".phtml": "PHP",
    # Ruby
    ".rb": "Ruby",
    ".rake": "Ruby",
    ".gemspec": "Ruby",
    # Shell
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    # HTML / CSS
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".scss": "CSS",
    ".sass": "CSS",
    # SQL
    ".sql": "SQL",
    # YAML / JSON / TOML (config, not really a "language" but commonly tracked)
    ".yaml": "YAML",
    ".yml": "YAML",
    ".json": "JSON",
    ".toml": "TOML",
    # Kotlin
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    # Swift
    ".swift": "Swift",
    # C#
    ".cs": "C#",
    # Scala
    ".scala": "Scala",
    # Markdown / docs
    ".md": "Markdown",
    ".rst": "reStructuredText",
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class LanguageStats:
    """Statistics for a single detected language."""

    name: str
    file_count: int
    byte_count: int

    @property
    def display_name(self) -> str:
        return self.name


@dataclasses.dataclass
class LanguageDetectionResult:
    """Aggregated language-detection outcome for a repository."""

    #: Languages ordered by file count descending.
    languages: list[LanguageStats] = dataclasses.field(default_factory=list)

    @property
    def primary_language(self) -> str | None:
        """The most common language, or None if nothing was detected."""
        return self.languages[0].name if self.languages else None

    @property
    def language_names(self) -> list[str]:
        return [lang.name for lang in self.languages]

    def by_name(self, name: str) -> LanguageStats | None:
        """Look up a :class:`LanguageStats` by language name (case-insensitive)."""
        name_lower = name.lower()
        for lang in self.languages:
            if lang.name.lower() == name_lower:
                return lang
        return None


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------


class LanguageDetector:
    """Derive language statistics from a :class:`~repomedic.scanner.models.ScanResult`.

    Parameters
    ----------
    extension_map:
        Custom extension → language mapping.  Defaults to
        :data:`EXTENSION_LANGUAGE_MAP`.
    """

    def __init__(self, extension_map: dict[str, str] | None = None) -> None:
        self._ext_map: dict[str, str] = (
            extension_map if extension_map is not None else EXTENSION_LANGUAGE_MAP
        )

    def detect(self, scan_result: ScanResult) -> LanguageDetectionResult:
        """Return a :class:`LanguageDetectionResult` derived from *scan_result*."""
        file_counts: Counter[str] = Counter()
        byte_counts: Counter[str] = Counter()

        for entry in scan_result.files:
            lang = self._language_for(entry)
            if lang:
                file_counts[lang] += 1
                byte_counts[lang] += entry.size_bytes

        stats = [
            LanguageStats(name=lang, file_count=file_counts[lang], byte_count=byte_counts[lang])
            for lang in sorted(file_counts, key=lambda l: (-file_counts[l], l))
        ]
        return LanguageDetectionResult(languages=stats)

    def _language_for(self, entry: FileEntry) -> str | None:
        """Return the language name for *entry*, or None if unrecognised."""
        return self._ext_map.get(entry.extension)
