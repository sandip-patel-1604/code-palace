"""Parsing engine — orchestrates file discovery and multi-language extraction."""

from __future__ import annotations

import fnmatch
from pathlib import Path

from palace.core.config import DEFAULT_EXCLUDE_PATTERNS
from palace.core.models import EXTENSION_TO_LANGUAGE
from palace.parsing.extractors.base import Extractor, FileExtraction
from palace.parsing.extractors.cpp import CppExtractor
from palace.parsing.extractors.go import GoExtractor
from palace.parsing.extractors.java import JavaExtractor
from palace.parsing.extractors.python import PythonExtractor
from palace.parsing.extractors.typescript import TypeScriptExtractor

# Files larger than 1 MB are skipped to avoid memory pressure
_MAX_FILE_BYTES = 1024 * 1024

# Heuristic: try UTF-8 decode; if that fails or >20% bytes are non-text control chars,
# treat as binary.  This catches both null-heavy binaries and high-byte-density data.
_BINARY_CHECK_BYTES = 8192


def _is_binary(data: bytes) -> bool:
    """Return True if the byte sample looks like a binary file.

    Uses two signals: non-decodable UTF-8 sequences, or a high ratio of raw
    bytes that cannot appear in human-readable source code (null, most C0 controls).
    """
    sample = data[:_BINARY_CHECK_BYTES]
    if not sample:
        return False
    # Signal 1: fails UTF-8 decoding entirely → binary
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return True
    # Signal 2: many null bytes → binary even if UTF-8 passes
    null_count = sample.count(0)
    return null_count > 0


def _matches_exclude(rel_parts: tuple[str, ...], patterns: list[str]) -> bool:
    """Return True if any path part matches an exclude pattern."""
    for pattern in patterns:
        for part in rel_parts:
            if fnmatch.fnmatch(part, pattern):
                return True
    return False


class ParsingEngine:
    """Discovers source files and dispatches parsing to registered extractors."""

    def __init__(self) -> None:
        self._extractors: dict[str, Extractor] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register the built-in language extractors."""
        for extractor in (
            PythonExtractor(),
            TypeScriptExtractor(),
            GoExtractor(),
            JavaExtractor(),
            CppExtractor(),
        ):
            self._extractors[extractor.language] = extractor  # type: ignore[attr-defined]

    def register(self, extractor: Extractor) -> None:
        """Register a custom extractor, replacing any existing one for the same language."""
        self._extractors[extractor.language] = extractor  # type: ignore[attr-defined]

    def detect_languages(self, root: Path) -> dict[str, int]:
        """Scan file extensions under root and return {language: file_count}."""
        counts: dict[str, int] = {}
        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue
            lang = EXTENSION_TO_LANGUAGE.get(file_path.suffix)
            if lang and lang in self._extractors:
                counts[lang] = counts.get(lang, 0) + 1
        return counts

    def parse_file(self, file_path: Path, root: Path) -> FileExtraction | None:
        """Read a single file and extract symbols.  Returns None on unrecognised extension."""
        lang = EXTENSION_TO_LANGUAGE.get(file_path.suffix)
        if lang is None:
            return None
        extractor = self._extractors.get(lang)
        if extractor is None:
            return None

        try:
            source = file_path.read_bytes()
        except OSError:
            return None

        return extractor.extract(source, file_path)  # type: ignore[attr-defined]

    def parse_all(
        self,
        root: Path,
        exclude: list[str] | None = None,
    ) -> list[FileExtraction]:
        """Discover and parse all supported source files under root.

        Skips files matching exclude patterns, files >1 MB, and binary files.
        """
        patterns = list(exclude) if exclude is not None else list(DEFAULT_EXCLUDE_PATTERNS)
        results: list[FileExtraction] = []

        for file_path in sorted(root.rglob("*")):
            if not file_path.is_file():
                continue

            # Skip excluded paths
            try:
                rel = file_path.relative_to(root)
            except ValueError:
                continue
            if _matches_exclude(rel.parts, patterns):
                continue

            # Skip unknown extensions
            lang = EXTENSION_TO_LANGUAGE.get(file_path.suffix)
            if lang is None or lang not in self._extractors:
                continue

            # Skip large files
            try:
                size = file_path.stat().st_size
            except OSError:
                continue
            if size > _MAX_FILE_BYTES:
                continue

            # Skip binary files
            try:
                raw = file_path.read_bytes()
            except OSError:
                continue
            if _is_binary(raw):
                continue

            extractor = self._extractors[lang]
            extraction = extractor.extract(raw, file_path)  # type: ignore[attr-defined]
            results.append(extraction)

        return results
