"""Scanner subsystem — file discovery, language detection, and project detection."""

from repomedic.scanner.file_scanner import DEFAULT_IGNORE_DIRS, FileScanner, ScanError
from repomedic.scanner.language_detector import (
    EXTENSION_LANGUAGE_MAP,
    LanguageDetectionResult,
    LanguageDetector,
    LanguageStats,
)
from repomedic.scanner.models import FileEntry, ScanResult
from repomedic.scanner.project_detector import (
    KNOWN_CONFIG_FILES,
    ConfigFileSpec,
    DetectedConfigFile,
    ProjectDetectionResult,
    ProjectDetector,
)

__all__ = [
    # file scanner
    "DEFAULT_IGNORE_DIRS",
    "FileEntry",
    "FileScanner",
    "ScanError",
    "ScanResult",
    # language detection
    "EXTENSION_LANGUAGE_MAP",
    "LanguageDetectionResult",
    "LanguageDetector",
    "LanguageStats",
    # project detection
    "KNOWN_CONFIG_FILES",
    "ConfigFileSpec",
    "DetectedConfigFile",
    "ProjectDetectionResult",
    "ProjectDetector",
]
