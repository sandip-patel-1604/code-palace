"""T_10 gate tests — Impact analyzer validation."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from palace.graph.impact import ImpactAnalyzer
from palace.storage.duckdb_store import DuckDBStore
from palace.storage.store import EdgeRecord, FileRecord, SymbolRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store() -> DuckDBStore:
    s = DuckDBStore(":memory:")
    s.initialize_schema()
    return s


def _chain(store: DuckDBStore) -> tuple[int, int, int]:
    """Create A → B → C import chain. Returns (fid_a, fid_b, fid_c)."""
    fid_c = store.upsert_file(FileRecord("c.py", "python", 50, 5, "hc"))
    fid_b = store.upsert_file(FileRecord("b.py", "python", 50, 5, "hb"))
    fid_a = store.upsert_file(FileRecord("a.py", "python", 50, 5, "ha"))
    # A imports B, B imports C
    store.upsert_edge(EdgeRecord(fid_a, "imports", fid_b))
    store.upsert_edge(EdgeRecord(fid_b, "imports", fid_c))
    return fid_a, fid_b, fid_c


def _add_churn(store: DuckDBStore, file_id: int, count: int) -> None:
    """Add `count` recent commits touching file_id."""
    now = datetime.now(tz=timezone.utc).isoformat()
    for i in range(count):
        cid = store.upsert_commit(f"sha_{file_id}_{i}", "dev", "d@t.com", now, f"msg{i}", 5, 2)
        path = None
        for f in store.get_all_files():
            if f["file_id"] == file_id:
                path = f["path"]
                break
        if path:
            store.upsert_file_change(cid, path, file_id, 5, 2, "M")


# ---------------------------------------------------------------------------
# T_10.2 — ImpactAnalyzer
# ---------------------------------------------------------------------------


class TestImpactAnalyzer:
    def test_file_impact(self, store: DuckDBStore) -> None:
        """T_10.2: File with 2 direct dependents reports correct count."""
        fid_a, fid_b, fid_c = _chain(store)
        # C is depended on by B (direct)
        analyzer = ImpactAnalyzer(store)
        result = analyzer.analyze_file(fid_c)
        assert result.direct_dependents == 1  # B depends on C
        # A→B→C so C has transitive = {B, A}
        assert result.transitive_dependents == 2

    def test_transitive(self, store: DuckDBStore) -> None:
        """T_10.2: Transitive dependents include full chain."""
        fid_a, fid_b, fid_c = _chain(store)
        result = ImpactAnalyzer(store).analyze_file(fid_c)
        assert result.transitive_dependents >= 2

    def test_risk_high(self, store: DuckDBStore) -> None:
        """T_10.2: Many dependents + high churn → HIGH risk."""
        # Create a hub file with many dependents
        hub = store.upsert_file(FileRecord("hub.py", "python", 100, 20, "h_hub"))
        for i in range(30):
            dep = store.upsert_file(FileRecord(f"dep_{i}.py", "python", 50, 5, f"hd{i}"))
            store.upsert_edge(EdgeRecord(dep, "imports", hub))
        _add_churn(store, hub, 20)
        result = ImpactAnalyzer(store).analyze_file(hub)
        assert result.risk == "HIGH"

    def test_risk_low(self, store: DuckDBStore) -> None:
        """T_10.2: Leaf file with 0 dependents → LOW risk."""
        leaf = store.upsert_file(FileRecord("leaf.py", "python", 30, 3, "hl"))
        result = ImpactAnalyzer(store).analyze_file(leaf)
        assert result.risk == "LOW"
        assert result.direct_dependents == 0

    def test_no_git_data(self, store: DuckDBStore) -> None:
        """T_10.2: Analyze without git history → empty cochange/ownership, no crash."""
        fid = store.upsert_file(FileRecord("solo.py", "python", 50, 5, "hs"))
        result = ImpactAnalyzer(store).analyze_file(fid)
        assert result.cochange_partners == []
        assert result.ownership == []
        assert result.churn is None

    def test_symbol_not_found(self, store: DuckDBStore) -> None:
        """T_10.2: Bad symbol name returns None."""
        fid = store.upsert_file(FileRecord("x.py", "python", 50, 5, "hx"))
        result = ImpactAnalyzer(store).analyze_symbol(fid, "nonexistent_function")
        assert result is None
