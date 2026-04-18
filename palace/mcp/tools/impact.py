"""MCP tool: palace_impact — blast-radius analysis for a file or symbol."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from palace.core.config import PalaceConfig
from palace.core.palace import Palace
from palace.core.resolve import resolve_file_target
from palace.graph.impact import ImpactAnalyzer, ImpactResult

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "target": {
            "type": "string",
            "description": "File path, or file.py:SymbolName.",
        },
        "depth": {
            "type": "integer",
            "description": "Max transitive depth.",
            "default": 10,
        },
    },
    "required": ["target"],
}


async def run(arguments: dict) -> str:
    target = arguments.get("target")
    if not target:
        return "Error: `target` is required."
    depth = int(arguments.get("depth", 10))

    config = PalaceConfig.discover(path=Path.cwd())
    if config is None:
        return "Error: No palace found. Run `palace init` first."

    palace = Palace(config)
    palace.open()
    try:
        assert palace.store is not None
        symbol_name: str | None = None
        file_path = target
        if ":" in target:
            file_path, symbol_name = target.rsplit(":", 1)

        file_row = resolve_file_target(palace.store, file_path, palace.config.root)
        if file_row is None:
            return f"Error: File `{file_path}` not found in the index."

        analyzer = ImpactAnalyzer(palace.store)
        file_id: int = file_row["file_id"]

        if symbol_name:
            result = analyzer.analyze_symbol(file_id, symbol_name)
            if result is None:
                return f"Error: Symbol `{symbol_name}` not found in {file_path}."
        else:
            result = analyzer.analyze_file(file_id, depth=depth)
    finally:
        palace.close()

    return _format(result, str(palace.config.root))


def _format(result: ImpactResult, root: str) -> str:
    short = result.path
    if short.startswith(root + "/"):
        short = short[len(root) + 1:]

    lines: list[str] = [
        "# Impact Analysis",
        "",
        f"**File:** `{short}`",
        f"**Risk:** {result.risk}",
        "",
        f"- Direct dependents: {result.direct_dependents}",
        f"- Transitive dependents: {result.transitive_dependents}",
    ]

    if result.domain_impact:
        domains = ", ".join(
            f"{d['name']} ({d['file_count']})" for d in result.domain_impact
        )
        lines.append(f"- Domain impact: {domains}")

    if result.ownership:
        top = result.ownership[0]
        lines.append(
            f"- Primary owner: {top['author_name']} ({top['commit_count']} commits)"
        )

    if result.churn:
        lines.append(f"- Churn (90d): {result.churn['change_count']} changes")

    if result.test_files:
        lines.append(f"- Test files: {len(result.test_files)}")
        for t in result.test_files[:5]:
            short_t = t
            if t.startswith(root + "/"):
                short_t = t[len(root) + 1:]
            lines.append(f"  - `{short_t}`")

    return "\n".join(lines)
