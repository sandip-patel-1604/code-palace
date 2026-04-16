"""Churn analysis — identify high-change-frequency hotspots."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from palace.storage.duckdb_store import DuckDBStore


class ChurnAnalyzer:
    """Thin wrapper over DuckDBStore churn operations."""

    def __init__(self, store: DuckDBStore) -> None:
        self._store = store

    def get_file_churn(self, file_id: int, days: int = 90) -> dict | None:
        """Return churn metrics for a single file, or None if no activity."""
        results = self._store.get_churn(file_id=file_id, days=days)
        return results[0] if results else None

    def get_hotspots(self, days: int = 90, limit: int = 20) -> list[dict]:
        """Return the most-changed files in the time window."""
        return self._store.get_churn(file_id=None, days=days)[:limit]
