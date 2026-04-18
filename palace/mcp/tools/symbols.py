"""MCP tool: palace_symbols — list and filter indexed symbols."""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

from palace.core.config import PalaceConfig
from palace.core.palace import Palace

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "kind": {
            "type": "string",
            "description": "Filter by symbol kind: function, class, method, etc.",
        },
        "file": {
            "type": "string",
            "description": "Filter by file path (glob supported).",
        },
        "pattern": {
            "type": "string",
            "description": "Filter by name (SQL LIKE: % and _ wildcards).",
        },
        "exported_only": {
            "type": "boolean",
            "description": "Show only exported symbols.",
            "default": False,
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of results.",
            "default": 50,
        },
    },
}


async def run(arguments: dict) -> str:
    kind = arguments.get("kind")
    file_glob = arguments.get("file")
    pattern = arguments.get("pattern")
    exported_only = bool(arguments.get("exported_only", False))
    limit = int(arguments.get("limit", 50))

    config = PalaceConfig.discover(path=Path.cwd())
    if config is None:
        return "Error: No palace found. Run `palace init` first."

    palace = Palace(config)
    palace.open()
    try:
        assert palace.store is not None
        store = palace.store
        root = str(palace.config.root)

        matched_files: list[dict] = []
        if file_glob is not None:
            all_files = store.get_all_files()
            matched_files = [f for f in all_files if fnmatch.fnmatch(f["path"], file_glob)]
            if not matched_files:
                matched_files = [
                    f
                    for f in all_files
                    if fnmatch.fnmatch(f["path"], f"{root}/{file_glob}")
                ]
            if not matched_files:
                return f"Error: No file matching `{file_glob}` found."

        name_pattern: str | None = None
        if pattern is not None:
            if "%" not in pattern and "_" not in pattern:
                name_pattern = f"%{pattern}%"
            else:
                name_pattern = pattern

        if matched_files and len(matched_files) > 1:
            symbols: list[dict] = []
            for f in matched_files:
                symbols.extend(
                    store.get_symbols(
                        file_id=f["file_id"],
                        kind=kind,
                        name_pattern=name_pattern,
                    )
                )
        else:
            file_id = matched_files[0]["file_id"] if matched_files else None
            symbols = store.get_symbols(
                file_id=file_id, kind=kind, name_pattern=name_pattern
            )

        if exported_only:
            symbols = [s for s in symbols if s.get("is_exported")]

        total = len(symbols)
        symbols = symbols[:limit]

        path_by_id: dict[int, str] = {}
        for s in symbols:
            fid = s["file_id"]
            if fid not in path_by_id:
                row = store.get_file_by_id(fid)
                path_by_id[fid] = row["path"] if row else str(fid)
    finally:
        palace.close()

    if total == 0:
        return "No symbols found."

    lines: list[str] = [f"# Symbols — {total} results (showing {len(symbols)})", ""]
    for s in symbols:
        path = path_by_id.get(s["file_id"], "")
        if path.startswith(root + "/"):
            path = path[len(root) + 1:]
        sig = s.get("signature") or ""
        sig_str = f" — `{sig}`" if sig else ""
        lines.append(
            f"- **{s['kind']}** `{s['name']}` — `{path}:{s['line_start']}`{sig_str}"
        )
    return "\n".join(lines)
