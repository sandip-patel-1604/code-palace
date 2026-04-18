"""MCP tool: palace_deps — query file dependencies (in/out/both)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from palace.core.config import PalaceConfig
from palace.core.palace import Palace
from palace.core.resolve import resolve_file_target

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "target": {
            "type": "string",
            "description": "File path to query dependencies for.",
        },
        "direction": {
            "type": "string",
            "description": "in (dependents), out (dependencies), or both.",
            "enum": ["in", "out", "both"],
            "default": "out",
        },
        "transitive": {
            "type": "boolean",
            "description": "Follow transitive dependencies.",
            "default": False,
        },
    },
    "required": ["target"],
}


async def run(arguments: dict) -> str:
    target = arguments.get("target")
    if not target:
        return "Error: `target` is required."
    direction = arguments.get("direction", "out")
    if direction not in ("in", "out", "both"):
        return "Error: `direction` must be one of in, out, both."
    transitive = bool(arguments.get("transitive", False))

    config = PalaceConfig.discover(path=Path.cwd())
    if config is None:
        return "Error: No palace found. Run `palace init` first."

    palace = Palace(config)
    palace.open()
    try:
        assert palace.store is not None
        file_row = resolve_file_target(palace.store, target, palace.config.root)
        if file_row is None:
            return f"Error: File `{target}` not found in the index."
        file_id: int = file_row["file_id"]

        out_deps: list[dict] = []
        in_deps: list[dict] = []
        if direction in ("out", "both"):
            out_deps = palace.store.get_dependencies(file_id, transitive=transitive)
        if direction in ("in", "both"):
            in_deps = palace.store.get_dependents(file_id, transitive=transitive)

        root = str(palace.config.root)
    finally:
        palace.close()

    target_short = _short(file_row["path"], root)
    lines: list[str] = [f"# Dependencies for `{target_short}`", ""]
    if direction in ("out", "both"):
        lines.append(f"## Dependencies (out) — {len(out_deps)}")
        for d in out_deps:
            lines.append(f"- `{_short(d['path'], root)}` [{d.get('language', '')}]")
        lines.append("")
    if direction in ("in", "both"):
        lines.append(f"## Dependents (in) — {len(in_deps)}")
        for d in in_deps:
            lines.append(f"- `{_short(d['path'], root)}` [{d.get('language', '')}]")
        lines.append("")
    if not out_deps and not in_deps:
        lines.append("_No dependencies found._")
    return "\n".join(lines)


def _short(path: str, root: str) -> str:
    if path.startswith(root + "/"):
        return path[len(root) + 1:]
    return path
