"""T_10 gate tests — Domain clustering validation."""

from __future__ import annotations

import pytest

from palace.graph.clustering import DomainClusterer
from palace.storage.duckdb_store import DuckDBStore
from palace.storage.store import EdgeRecord, FileRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store() -> DuckDBStore:
    s = DuckDBStore(":memory:")
    s.initialize_schema()
    return s


def _make_two_clusters(store: DuckDBStore) -> dict[str, list[int]]:
    """Create 6 files in 2 import groups of 3. Returns {group: [file_ids]}."""
    group_a = []
    for name in ["src/auth/login.py", "src/auth/session.py", "src/auth/token.py"]:
        fid = store.upsert_file(FileRecord(name, "python", 100, 10, f"h_{name}"))
        group_a.append(fid)
    group_b = []
    for name in ["src/api/routes.py", "src/api/handlers.py", "src/api/middleware.py"]:
        fid = store.upsert_file(FileRecord(name, "python", 100, 10, f"h_{name}"))
        group_b.append(fid)
    # Intra-group import edges
    for g in [group_a, group_b]:
        for i in range(len(g)):
            for j in range(len(g)):
                if i != j:
                    store.upsert_edge(EdgeRecord(g[i], "imports", g[j]))
    return {"auth": group_a, "api": group_b}


# ---------------------------------------------------------------------------
# T_10.1 — DomainClusterer
# ---------------------------------------------------------------------------


class TestDomainClusterer:
    def test_cluster_two_groups(self, store: DuckDBStore) -> None:
        """T_10.1: Two import groups of 3 files produce 2 domains."""
        _make_two_clusters(store)
        clusterer = DomainClusterer(store)
        domains = clusterer.cluster(min_files=2)
        # Should have at least 2 real domains (possibly + Other)
        real = [d for d in domains if d["name"] != "Other"]
        assert len(real) >= 2

    def test_single_file(self, store: DuckDBStore) -> None:
        """T_10.1: Single file produces 1 domain, no crash."""
        store.upsert_file(FileRecord("solo.py", "python", 50, 5, "h1"))
        clusterer = DomainClusterer(store)
        domains = clusterer.cluster()
        assert len(domains) == 1
        assert domains[0]["file_count"] == 1

    def test_auto_naming(self, store: DuckDBStore) -> None:
        """T_10.1: Files in src/auth/ get a domain name containing 'auth'."""
        groups = _make_two_clusters(store)
        clusterer = DomainClusterer(store)
        domains = clusterer.cluster(min_files=2)
        names_lower = [d["name"].lower() for d in domains]
        assert any("auth" in n for n in names_lower)

    def test_re_cluster(self, store: DuckDBStore) -> None:
        """T_10.1: Running cluster() twice produces same count, no duplicates."""
        _make_two_clusters(store)
        clusterer = DomainClusterer(store)
        d1 = clusterer.cluster(min_files=2)
        d2 = clusterer.cluster(min_files=2)
        assert len(d1) == len(d2)
        # Verify no leftover domains from first run
        all_domains = store.get_domains()
        assert len(all_domains) == len(d2)

    def test_empty_codebase(self, store: DuckDBStore) -> None:
        """T_10.1: Zero files produces empty domain list."""
        clusterer = DomainClusterer(store)
        domains = clusterer.cluster()
        assert domains == []


# ---------------------------------------------------------------------------
# T_14.5 — Clustering N+1 fix and encapsulation
# ---------------------------------------------------------------------------


class TestBulkCochangeAndClearDomains:
    """T_14.5: Bulk cochange query and clear_domains encapsulation."""

    def test_get_all_cochange_pairs_structure(self, store: DuckDBStore) -> None:
        """T_14.5.1: get_all_cochange_pairs returns dicts with correct keys."""
        # Set up: two files co-changing in 3 commits
        fid_a = store.upsert_file(FileRecord("a.py", "python", 50, 5, "ha"))
        fid_b = store.upsert_file(FileRecord("b.py", "python", 50, 5, "hb"))
        for i in range(3):
            cid = store.upsert_commit(f"sha{i}", "dev", "dev@x.com", "2024-01-01", f"msg{i}", 1, 0)
            store.upsert_file_change(cid, "a.py", fid_a, 1, 0, "M")
            store.upsert_file_change(cid, "b.py", fid_b, 1, 0, "M")
        store.materialize_cochange(min_co_commits=3)

        pairs = store.get_all_cochange_pairs(min_co_commits=3)
        assert len(pairs) >= 1
        pair = pairs[0]
        assert "file_id_a" in pair
        assert "file_id_b" in pair
        assert "co_commits" in pair
        assert "confidence" in pair

    def test_get_all_cochange_pairs_filter(self, store: DuckDBStore) -> None:
        """T_14.5.2: min_co_commits filter is applied correctly."""
        fid_a = store.upsert_file(FileRecord("x.py", "python", 50, 5, "hx"))
        fid_b = store.upsert_file(FileRecord("y.py", "python", 50, 5, "hy"))
        for i in range(3):
            cid = store.upsert_commit(f"s{i}", "dev", "d@x.com", "2024-01-01", f"m{i}", 1, 0)
            store.upsert_file_change(cid, "x.py", fid_a, 1, 0, "M")
            store.upsert_file_change(cid, "y.py", fid_b, 1, 0, "M")
        store.materialize_cochange(min_co_commits=2)

        # Should find pairs with co_commits >= 5 = none (only 3 co-commits)
        pairs_high = store.get_all_cochange_pairs(min_co_commits=5)
        assert len(pairs_high) == 0

        # Should find pairs with co_commits >= 3
        pairs_low = store.get_all_cochange_pairs(min_co_commits=3)
        assert len(pairs_low) >= 1
        for p in pairs_low:
            assert p["co_commits"] >= 3

    def test_clear_domains(self, store: DuckDBStore) -> None:
        """T_14.5.3: clear_domains removes all domain and file_domain rows."""
        fid = store.upsert_file(FileRecord("c.py", "python", 50, 5, "hc"))
        did = store.upsert_domain("TestDomain")
        store.assign_file_to_domain(fid, did)

        assert len(store.get_domains()) == 1
        store.clear_domains()
        assert len(store.get_domains()) == 0

    def test_clustering_equivalence(self, store: DuckDBStore) -> None:
        """T_14.5.4: Clustering with bulk query produces valid domains."""
        _make_two_clusters(store)
        clusterer = DomainClusterer(store)
        domains = clusterer.cluster(min_files=2)
        # Should produce at least 2 domains (the two clusters)
        assert len(domains) >= 2
        total_files = sum(d["file_count"] for d in domains)
        assert total_files > 0
