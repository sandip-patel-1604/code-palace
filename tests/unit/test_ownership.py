"""T_8 gate tests — Ownership analyzer validation."""

from __future__ import annotations

import pytest

from palace.storage.duckdb_store import DuckDBStore
from palace.storage.store import FileRecord
from palace.temporal.ownership import OwnershipAnalyzer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store() -> DuckDBStore:
    s = DuckDBStore(":memory:")
    s.initialize_schema()
    return s


def _setup_git_data(store: DuckDBStore) -> int:
    """Insert 1 file + 3 commits (alice x2, bob x1). Returns file_id."""
    fid = store.upsert_file(FileRecord("a.py", "python", 100, 10, "h1"))
    for i, (sha, name) in enumerate([("aaa", "alice"), ("bbb", "bob"), ("ccc", "alice")]):
        cid = store.upsert_commit(sha, name, f"{name}@test.com", f"2025-01-0{i + 1}", f"msg{i}", 10, 5)
        store.upsert_file_change(cid, "a.py", fid, 5, 2, "M")
    return fid


# ---------------------------------------------------------------------------
# T_8.5 — Ownership analyzer
# ---------------------------------------------------------------------------


class TestOwnershipAnalyzer:
    def test_get_owners(self, store: DuckDBStore) -> None:
        """T_8.5: Two authors returned, alice has 2 commits, bob has 1."""
        fid = _setup_git_data(store)
        analyzer = OwnershipAnalyzer(store)
        owners = analyzer.get_owners(fid)
        assert len(owners) == 2
        by_name = {o["author_name"]: o for o in owners}
        assert by_name["alice"]["commit_count"] == 2
        assert by_name["bob"]["commit_count"] == 1

    def test_primary_owner(self, store: DuckDBStore) -> None:
        """T_8.5: Primary owner is alice (most commits)."""
        fid = _setup_git_data(store)
        analyzer = OwnershipAnalyzer(store)
        primary = analyzer.get_primary_owner(fid)
        assert primary is not None
        assert primary["author_name"] == "alice"

    def test_empty_file(self, store: DuckDBStore) -> None:
        """T_8.5: File with no git history returns None for primary owner."""
        fid = store.upsert_file(FileRecord("new.py", "python", 50, 5, "h9"))
        analyzer = OwnershipAnalyzer(store)
        assert analyzer.get_primary_owner(fid) is None
        assert analyzer.get_owners(fid) == []
