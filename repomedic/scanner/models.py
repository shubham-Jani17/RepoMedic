"""Data models for scanner results."""

from __future__ import annotations

import dataclasses
from collections import Counter
from pathlib import Path


@dataclasses.dataclass(frozen=True, slots=True)
class FileEntry:
    """Metadata for a single discovered file."""

    absolute_path: Path
    relative_path: Path
    filename: str
    extension: str  # lower-cased, includes leading dot; empty string for no extension
    size_bytes: int

    @classmethod
    def from_path(cls, absolute: Path, root: Path) -> "FileEntry":
        """Construct a FileEntry given an absolute path and the scan root."""
        return cls(
            absolute_path=absolute,
            relative_path=absolute.relative_to(root),
            filename=absolute.name,
            extension=absolute.suffix.lower(),
            size_bytes=absolute.stat().st_size,
        )


@dataclasses.dataclass
class ScanResult:
    """Aggregated result of a repository scan."""

    root: Path
    files: list[FileEntry] = dataclasses.field(default_factory=list)
    ignored_dirs: list[str] = dataclasses.field(default_factory=list)
    errors: list[str] = dataclasses.field(default_factory=list)

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def extension_counts(self) -> dict[str, int]:
        """Map of file extension → count, sorted by frequency descending."""
        raw = Counter(f.extension or "(no extension)" for f in self.files)
        return dict(raw.most_common())

    @property
    def total_size_bytes(self) -> int:
        return sum(f.size_bytes for f in self.files)
