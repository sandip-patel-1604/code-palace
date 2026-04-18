"""Shared file-target resolution for CLI commands and MCP tools."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from palace.storage.duckdb_store import DuckDBStore


def resolve_file_target(
    store: DuckDBStore,
    target: str,
    project_root: Path,
) -> dict | None:
    """Find the file record matching a target path.

    Resolution strategy (first match wins):
      1. Exact match against stored path.
      2. Resolve relative to project_root and try again.
      3. Scan all files and match by path suffix (ends-with).
    """
    # 1. Exact match
    row = store.get_file_by_path(target)
    if row is not None:
        return row

    # 2. Relative to project root
    target_path = Path(target)
    if not target_path.is_absolute():
        candidate = str(project_root / target_path)
        row = store.get_file_by_path(candidate)
        if row is not None:
            return row

    # 3. Suffix match
    suffix = target.lstrip("/")
    for f in store.get_all_files():
        if f["path"].endswith(suffix):
            return f

    return None
