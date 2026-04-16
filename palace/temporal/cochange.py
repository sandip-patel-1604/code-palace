"""Co-change analysis — identify files that frequently change together."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from palace.storage.duckdb_store import DuckDBStore


class CoChangeAnalyzer:
    """Thin wrapper over DuckDBStore co-change operations."""

    def __init__(self, store: DuckDBStore) -> None:
        self._store = store

    def materialize(self, min_co_commits: int = 3) -> int:
        """Compute and store co-change pairs. Returns pair count."""
        return self._store.materialize_cochange(min_co_commits)

    def get_partners(self, file_id: int, min_co_commits: int = 3) -> list[dict]:
        """Get files that frequently change alongside file_id."""
        return self._store.get_cochange_pairs(file_id, min_co_commits)
