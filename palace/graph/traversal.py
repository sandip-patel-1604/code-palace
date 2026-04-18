"""Graph traversal algorithms for the Code Palace symbol graph."""

from __future__ import annotations

from collections import deque

from palace.core.models import EdgeType
from palace.storage.duckdb_store import DuckDBStore


def topological_sort(
    store: DuckDBStore,
    file_ids: set[int] | None = None,
) -> list[int]:
    """Return file_ids in dependency order (leaves first) using Kahn's algorithm.

    If file_ids is provided, only the subgraph induced by those IDs is sorted.
    Files with no outgoing import edges appear first (they are dependencies).
    """
    # Determine the working set
    if file_ids is not None:
        working = set(file_ids)
    else:
        working = {f["file_id"] for f in store.get_all_files()}

    # Build adjacency structures: for each node, who does it import (in-edges for dependents)
    # Kahn's: count in-degrees (number of dependencies that must precede a file)
    in_degree: dict[int, int] = {fid: 0 for fid in working}
    # adj maps: fid -> set of files that import fid (reverse edges for propagation)
    dependents: dict[int, list[int]] = {fid: [] for fid in working}

    edges = store.get_edges(edge_type=str(EdgeType.IMPORTS))
    for edge in edges:
        src = edge["source_file_id"]
        tgt = edge["target_file_id"]
        if tgt is None:
            continue
        if src not in working or tgt not in working:
            continue
        # src imports tgt — so src has in-degree from tgt's perspective
        in_degree[src] = in_degree.get(src, 0) + 1
        dependents[tgt].append(src)

    # Queue starts with nodes that have zero in-degree (no dependencies in the set)
    queue: deque[int] = deque(fid for fid in working if in_degree[fid] == 0)
    result: list[int] = []

    while queue:
        node = queue.popleft()
        result.append(node)
        for dependent in dependents.get(node, []):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    # If there is a cycle some nodes are never appended — append them in stable order
    remaining = [fid for fid in sorted(working) if fid not in set(result)]
    result.extend(remaining)

    return result


def get_dependency_tree(
    store: DuckDBStore,
    file_id: int,
    max_depth: int = 10,
) -> dict:
    """Return a nested dict representing the dependency tree rooted at file_id.

    Each node has keys: file_id, path, language, children (list of nodes).
    Visited set prevents infinite recursion on cyclic graphs.
    """
    visited: set[int] = set()

    def _build(fid: int, depth: int) -> dict:
        file_row = store.get_file_by_id(fid)
        node: dict = {
            "file_id": fid,
            "path": file_row["path"] if file_row else "",
            "language": file_row["language"] if file_row else "",
            "children": [],
        }
        if depth >= max_depth or fid in visited:
            return node
        visited.add(fid)

        deps = store.get_dependencies(fid, transitive=False)
        for dep in deps:
            child_id = dep["file_id"]
            node["children"].append(_build(child_id, depth + 1))

        return node

    return _build(file_id, 0)


