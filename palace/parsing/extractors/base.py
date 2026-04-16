"""Base data models and Extractor protocol for Code Palace parsing layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from palace.core.models import SymbolKind


@dataclass
class SymbolInfo:
    """All information extracted about a single named symbol."""

    name: str
    qualified_name: str
    kind: SymbolKind
    line_start: int
    line_end: int
    col_start: int
    col_end: int
    signature: str | None = None
    docstring: str | None = None
    is_exported: bool = True
    parent_name: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ImportInfo:
    """A single import statement extracted from a source file."""

    module_path: str
    imported_names: list[str] = field(default_factory=list)
    alias: str | None = None
    is_relative: bool = False
    line_number: int = 0


@dataclass
class FileExtraction:
    """All symbols and imports extracted from a single source file."""

    path: Path
    language: str
    symbols: list[SymbolInfo] = field(default_factory=list)
    imports: list[ImportInfo] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@runtime_checkable
class Extractor(Protocol):
    """Protocol for language-specific AST symbol extractors."""

    language: str
    extensions: list[str]

    def extract(self, source: bytes, file_path: Path) -> FileExtraction:
        """Parse source bytes and return all symbols and imports found."""
        ...
