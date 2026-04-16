"""T_8 gate tests — Churn analyzer validation."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from palace.storage.duckdb_store import DuckDBStore
from palace.storage.store import FileRecord
from palace.temporal.churn import ChurnAnalyzer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store() -> DuckDBStore:
    s = DuckDBStore(":memory:")
    s.initialize_schema()
    return s


def _setup_git_data(store: DuckDBStore) -> tuple[int, int]:
    """Insert 2 files, 3 commits touching both with recent dates. Returns (fid_a, fid_b)."""
    fid_a = store.upsert_file(FileRecord("a.py", "python", 100, 10, "h1"))
    fid_b = store.upsert_file(FileRecord("b.py", "python", 200, 20, "h2"))
    now = datetime.now(tz=timezone.utc)
    for i, sha in enumerate(["aaa", "bbb", "ccc"]):
        # Use today's date so commits fall within any reasonable time window
        ts = now.isoformat()
        cid = store.upsert_commit(sha, "alice", "a@t.com", ts, f"msg{i}", 10, 5)
        store.upsert_file_change(cid, "a.py", fid_a, 5, 2, "M")
        store.upsert_file_change(cid, "b.py", fid_b, 3, 1, "M")
    return fid_a, fid_b


# ---------------------------------------------------------------------------
# T_8.6 — Churn analyzer
# ---------------------------------------------------------------------------


class TestChurnAnalyzer:
    def test_file_churn(self, store: DuckDBStore) -> None:
        """T_8.6: File a has 3 changes within window."""
        fid_a, _ = _setup_git_data(store)
        analyzer = ChurnAnalyzer(store)
        churn = analyzer.get_file_churn(fid_a, days=365)
        assert churn is not None
        assert churn["change_count"] == 3

    def test_hotspots(self, store: DuckDBStore) -> None:
        """T_8.6: Hotspots returns both files sorted by change count."""
        _setup_git_data(store)
        analyzer = ChurnAnalyzer(store)
        hotspots = analyzer.get_hotspots(days=365)
        assert len(hotspots) == 2
        # Both have 3 changes
        assert all(h["change_count"] == 3 for h in hotspots)

    def test_empty(self, store: DuckDBStore) -> None:
        """T_8.6: File with no history returns None."""
        fid = store.upsert_file(FileRecord("new.py", "python", 50, 5, "h9"))
        analyzer = ChurnAnalyzer(store)
        assert analyzer.get_file_churn(fid, days=365) is None
