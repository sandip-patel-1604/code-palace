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
