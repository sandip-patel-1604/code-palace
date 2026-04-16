"""Code ownership analysis — identify per-file author contributions."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from palace.storage.duckdb_store import DuckDBStore


class OwnershipAnalyzer:
    """Thin wrapper over DuckDBStore ownership operations."""

    def __init__(self, store: DuckDBStore) -> None:
        self._store = store

    def get_owners(self, file_id: int) -> list[dict]:
        """Return author breakdown for a file, sorted by commit count."""
        return self._store.get_file_ownership(file_id)

    def get_primary_owner(self, file_id: int) -> dict | None:
        """Return the top contributor for a file, or None if no history."""
        owners = self._store.get_file_ownership(file_id)
        return owners[0] if owners else None
