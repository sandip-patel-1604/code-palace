"""Store protocol and data record types for Code Palace storage layer."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class FileRecord:
    """Input record for inserting/upserting a source file."""

    path: str
    language: str
    size_bytes: int
    line_count: int
    hash: str


@dataclass
class SymbolRecord:
    """Input record for inserting a symbol extracted from an AST."""

    file_id: int
    name: str
    qualified_name: str
    kind: str
    line_start: int
    line_end: int
    col_start: int
    col_end: int
    parent_id: int | None = None
    signature: str | None = None
    docstring: str | None = None
    is_exported: bool = True
    metadata: dict | None = None


@dataclass
class EdgeRecord:
    """Input record for inserting a directed relationship edge."""

    source_file_id: int
    edge_type: str
    # All FK columns are optional — edges may connect files without symbol resolution
    target_file_id: int | None = None
    source_symbol_id: int | None = None
    target_symbol_id: int | None = None
    weight: float = 1.0
    metadata: dict | None = None


@dataclass
class ImportRecord:
    """Input record for inserting a raw import declaration."""

    file_id: int
    module_path: str
    line_number: int
    imported_names: str | None = None
    alias: str | None = None
    is_relative: bool = False
    resolved_file_id: int | None = None


@runtime_checkable
class Store(Protocol):
    """Protocol defining the storage interface for Code Palace.

    All implementations must provide the methods below.  Return types for
    query methods use plain dicts for flexibility — callers pattern-match on
    keys rather than depending on a concrete class.
    """

    def initialize_schema(self) -> None:
        """Create all tables, sequences, and indexes.  Must be idempotent."""
        ...

    def upsert_file(self, record: FileRecord) -> int:
        """Insert or update a file row.  Returns the file_id."""
        ...

    def upsert_symbol(self, record: SymbolRecord) -> int:
        """Insert a symbol row.  Returns the symbol_id."""
        ...

    def upsert_edge(self, record: EdgeRecord) -> None:
        """Insert an edge row."""
        ...

    def get_symbols(
        self,
        file_id: int | None = None,
        kind: str | None = None,
        name_pattern: str | None = None,
    ) -> list[dict]:
        """Return symbols, optionally filtered by file, kind, or name glob."""
        ...

    def get_edges(
        self,
        source_file_id: int | None = None,
        target_file_id: int | None = None,
        edge_type: str | None = None,
    ) -> list[dict]:
        """Return edges, optionally filtered by source, target, or type."""
        ...

    def get_dependents(self, file_id: int, transitive: bool = False) -> list[dict]:
        """Return files that depend on (import) file_id.

        If transitive=True, walks the full import graph upward and includes a
        'depth' key in each result row.
        """
        ...

    def get_dependencies(self, file_id: int, transitive: bool = False) -> list[dict]:
        """Return files that file_id depends on (imports).

        If transitive=True, walks the full import graph downward and includes a
        'depth' key in each result row.
        """
        ...

    def get_file_by_path(self, path: str) -> dict | None:
        """Return the file row for path, or None if not found."""
        ...

    def get_all_files(self) -> list[dict]:
        """Return all file rows."""
        ...

    def upsert_import(self, record: ImportRecord) -> int:
        """Insert an import declaration row.  Returns the import_id."""
        ...

    def resolve_import(self, import_id: int, resolved_file_id: int) -> None:
        """Update resolved_file_id for a previously-inserted import row."""
        ...

    def get_imports(self, file_id: int | None = None) -> list[dict]:
        """Return import rows, optionally filtered to a specific file."""
        ...

    def set_meta(self, key: str, value: str) -> None:
        """Persist a key/value metadata entry."""
        ...

    def get_meta(self, key: str) -> str | None:
        """Retrieve a metadata value by key, or None if absent."""
        ...

    def clear(self) -> None:
        """Delete all data rows while preserving the schema.

        Used before re-indexing with --force so IDs reset cleanly.
        """
        ...

    def close(self) -> None:
        """Close the underlying database connection."""
        ...


# ---------------------------------------------------------------------------
# Phase 2 protocols — additive, do not modify Store above
# ---------------------------------------------------------------------------


@runtime_checkable
class TemporalStore(Protocol):
    """Protocol for git history storage operations."""

    def upsert_commit(
        self,
        sha: str,
        author_name: str,
        author_email: str,
        committed_at: str,
        message: str,
        insertions: int,
        deletions: int,
    ) -> int:
        """Insert a git commit row. Returns the commit_id."""
        ...

    def upsert_file_change(
        self,
        commit_id: int,
        file_path: str,
        file_id: int | None,
        insertions: int | None,
        deletions: int | None,
        change_type: str,
    ) -> None:
        """Insert a per-file change within a commit."""
        ...

    def materialize_cochange(self, min_co_commits: int = 3) -> int:
        """Compute cochange_pairs from git_file_changes. Returns pair count."""
        ...

    def get_cochange_pairs(self, file_id: int, min_co_commits: int = 3) -> list[dict]:
        """Return files that frequently change alongside file_id."""
        ...

    def get_file_ownership(self, file_id: int) -> list[dict]:
        """Return author contribution breakdown for a file."""
        ...

    def get_churn(self, file_id: int | None = None, days: int = 90) -> list[dict]:
        """Return change-frequency metrics, optionally filtered to one file."""
        ...

    def get_commit_count(self) -> int:
        """Return total number of stored commits."""
        ...


@runtime_checkable
class DomainStore(Protocol):
    """Protocol for domain clustering storage."""

    def upsert_domain(
        self,
        name: str,
        description: str | None = None,
        color: str | None = None,
    ) -> int:
        """Insert a domain cluster. Returns the domain_id."""
        ...

    def assign_file_to_domain(
        self,
        file_id: int,
        domain_id: int,
        confidence: float = 1.0,
    ) -> None:
        """Map a file to a domain cluster."""
        ...

    def get_domains(self) -> list[dict]:
        """Return all domain clusters."""
        ...

    def get_domain_files(self, domain_id: int) -> list[dict]:
        """Return files assigned to a domain."""
        ...

    def get_file_domain(self, file_id: int) -> dict | None:
        """Return the domain assignment for a file, or None."""
        ...


@runtime_checkable
class VectorStore(Protocol):
    """Protocol for 768-dim vector embedding storage and similarity search.

    Backed by LanceDB.  Keeps symbol embeddings and file embeddings in
    separate tables so searches can be scoped without cross-table noise.
    """

    def upsert_symbol_embedding(
        self,
        symbol_id: int,
        file_id: int,
        name: str,
        qualified_name: str,
        kind: str,
        file_path: str,
        text: str,
        vector: list[float],
    ) -> None:
        """Store or overwrite the embedding for a symbol.

        If a row with the same symbol_id already exists it is replaced.
        """
        ...

    def upsert_file_embedding(
        self,
        file_id: int,
        path: str,
        language: str,
        text: str,
        vector: list[float],
    ) -> None:
        """Store or overwrite the embedding for a file.

        If a row with the same file_id already exists it is replaced.
        """
        ...

    def search_symbols(
        self,
        query_vector: list[float],
        limit: int = 20,
        kind: str | None = None,
    ) -> list[dict]:
        """Vector similarity search over symbol embeddings.

        Returns a list of dicts with keys:
            symbol_id, file_id, name, qualified_name, kind, file_path, score
        where score is 1 - _distance (higher = more similar).
        """
        ...

    def search_files(
        self,
        query_vector: list[float],
        limit: int = 20,
        language: str | None = None,
    ) -> list[dict]:
        """Vector similarity search over file embeddings.

        Returns a list of dicts with keys:
            file_id, path, language, score
        where score is 1 - _distance (higher = more similar).
        """
        ...

    def clear(self) -> None:
        """Drop both embedding tables, resetting the store to empty."""
        ...

    def close(self) -> None:
        """Close the underlying LanceDB connection."""
        ...
