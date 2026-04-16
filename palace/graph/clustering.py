"""Domain clustering — group files into named domains via Louvain community detection."""

from __future__ import annotations

from collections import Counter
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

import networkx as nx

from palace.core.models import EdgeType

if TYPE_CHECKING:
    from palace.storage.duckdb_store import DuckDBStore


class DomainClusterer:
    """Cluster files into domains using import graph + optional co-change signals."""

    def __init__(self, store: DuckDBStore) -> None:
        self._store = store

    def cluster(self, min_files: int = 2) -> list[dict]:
        """Compute domain clusters and store in DuckDB.

        Returns list of dicts: [{domain_id, name, file_count}, ...].
        """
        all_files = self._store.get_all_files()
        if len(all_files) <= 1:
            return self._single_domain(all_files)

        graph = self._build_graph(all_files)

        # Louvain needs at least one edge; fall back to single domain
        if graph.number_of_edges() == 0:
            return self._single_domain(all_files)

        communities = nx.community.louvain_communities(graph, weight="weight", seed=42)

        # Split into real clusters and small leftovers
        clusters: list[set[int]] = []
        other: set[int] = set()
        for community in communities:
            if len(community) >= min_files:
                clusters.append(set(community))
            else:
                other.update(community)

        # If everything ended up in "other", make one big domain
        if not clusters:
            return self._single_domain(all_files)

        # Clear old domain assignments
        self._store._con.execute("DELETE FROM file_domains")
        self._store._con.execute("DELETE FROM domains")

        # Build file_id → path lookup
        path_map = {f["file_id"]: f["path"] for f in all_files}

        results: list[dict] = []
        for cluster_ids in clusters:
            paths = [path_map[fid] for fid in cluster_ids if fid in path_map]
            name = _auto_name(paths, len(results) + 1)
            domain_id = self._store.upsert_domain(name)
            for fid in cluster_ids:
                self._store.assign_file_to_domain(fid, domain_id)
            results.append({"domain_id": domain_id, "name": name, "file_count": len(cluster_ids)})

        # Assign leftovers to "Other" domain
        if other:
            other_id = self._store.upsert_domain("Other")
            for fid in other:
                self._store.assign_file_to_domain(fid, other_id)
            results.append({"domain_id": other_id, "name": "Other", "file_count": len(other)})

        return results

    def _build_graph(self, all_files: list[dict]) -> nx.Graph:
        """Build weighted graph from import edges + optional co-change data."""
        graph = nx.Graph()
        file_ids = {f["file_id"] for f in all_files}
        for fid in file_ids:
            graph.add_node(fid)

        # Import edges (weight 3.0)
        edges = self._store.get_edges(edge_type=str(EdgeType.IMPORTS))
        for edge in edges:
            src = edge["source_file_id"]
            tgt = edge["target_file_id"]
            if tgt is None or src not in file_ids or tgt not in file_ids:
                continue
            if graph.has_edge(src, tgt):
                graph[src][tgt]["weight"] += 3.0
            else:
                graph.add_edge(src, tgt, weight=3.0)

        # Co-change edges (weight = min(co_commits/5, 2.0))
        for fid in file_ids:
            try:
                partners = self._store.get_cochange_pairs(fid, min_co_commits=2)
            except Exception:
                continue
            for p in partners:
                pid = p["partner_id"]
                if pid not in file_ids:
                    continue
                w = min(p["co_commits"] / 5.0, 2.0)
                if graph.has_edge(fid, pid):
                    graph[fid][pid]["weight"] += w
                else:
                    graph.add_edge(fid, pid, weight=w)

        return graph

    def _single_domain(self, all_files: list[dict]) -> list[dict]:
        """Fallback: assign all files to one domain."""
        self._store._con.execute("DELETE FROM file_domains")
        self._store._con.execute("DELETE FROM domains")
        if not all_files:
            return []
        domain_id = self._store.upsert_domain("All Files")
        for f in all_files:
            self._store.assign_file_to_domain(f["file_id"], domain_id)
        return [{"domain_id": domain_id, "name": "All Files", "file_count": len(all_files)}]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _auto_name(paths: list[str], index: int) -> str:
    """Generate a human-readable name from the most common directory component."""
    if not paths:
        return f"Group {index}"

    # Count directory components across all paths
    component_counts: Counter[str] = Counter()
    for path in paths:
        parts = PurePosixPath(path).parts
        # Skip filename, count directories only
        for part in parts[:-1]:
            # Skip generic parts
            if part in (".", "..", "src", "lib", "palace"):
                continue
            component_counts[part] += 1

    if not component_counts:
        # No meaningful directory — use common filename stems
        stems = [PurePosixPath(p).stem for p in paths]
        stem_counts: Counter[str] = Counter(stems)
        most_common_stem = stem_counts.most_common(1)
        if most_common_stem:
            return most_common_stem[0][0].replace("_", " ").title()
        return f"Group {index}"

    best = component_counts.most_common(1)[0][0]
    return best.replace("_", " ").title()
