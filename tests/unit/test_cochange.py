"""T_8 gate tests — Co-change analyzer validation."""

from __future__ import annotations

import pytest

from palace.storage.duckdb_store import DuckDBStore
from palace.storage.store import FileRecord
from palace.temporal.cochange import CoChangeAnalyzer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store() -> DuckDBStore:
    s = DuckDBStore(":memory:")
    s.initialize_schema()
    return s


def _setup_git_data(store: DuckDBStore) -> tuple[int, int]:
    """Insert 2 files + 3 commits where both files change together."""
    fid_a = store.upsert_file(FileRecord("a.py", "python", 100, 10, "h1"))
    fid_b = store.upsert_file(FileRecord("b.py", "python", 200, 20, "h2"))
    for i, (sha, name) in enumerate([("aaa", "alice"), ("bbb", "bob"), ("ccc", "alice")]):
        cid = store.upsert_commit(sha, name, f"{name}@test.com", f"2025-01-0{i + 1}", f"msg{i}", 10, 5)
        store.upsert_file_change(cid, "a.py", fid_a, 5, 2, "M")
        store.upsert_file_change(cid, "b.py", fid_b, 3, 1, "M")
    return fid_a, fid_b


# ---------------------------------------------------------------------------
# T_8.4 — Co-change analyzer
# ---------------------------------------------------------------------------


class TestCoChangeAnalyzer:
    def test_materialize(self, store: DuckDBStore) -> None:
        """T_8.4: materialize returns pair count > 0 when files co-change."""
        fid_a, fid_b = _setup_git_data(store)
        analyzer = CoChangeAnalyzer(store)
        count = analyzer.materialize(min_co_commits=3)
        assert count >= 1

    def test_canonical_ordering(self, store: DuckDBStore) -> None:
        """T_8.4: All cochange pairs have file_id_a < file_id_b in the database."""
        _setup_git_data(store)
        CoChangeAnalyzer(store).materialize(min_co_commits=3)
        rows = store._con.execute("SELECT file_id_a, file_id_b FROM cochange_pairs").fetchall()
        for a, b in rows:
            assert a < b

    def test_idempotency(self, store: DuckDBStore) -> None:
        """T_8.4: Running materialize twice produces the same count."""
        _setup_git_data(store)
        analyzer = CoChangeAnalyzer(store)
        c1 = analyzer.materialize(min_co_commits=3)
        c2 = analyzer.materialize(min_co_commits=3)
        assert c1 == c2

    def test_get_partners(self, store: DuckDBStore) -> None:
        """T_8.4: get_partners returns the correct co-change partner."""
        fid_a, fid_b = _setup_git_data(store)
        analyzer = CoChangeAnalyzer(store)
        analyzer.materialize(min_co_commits=3)
        partners = analyzer.get_partners(fid_a, min_co_commits=3)
        partner_ids = [p["partner_id"] for p in partners]
        assert fid_b in partner_ids
