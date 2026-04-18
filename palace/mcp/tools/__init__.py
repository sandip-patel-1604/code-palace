"""MCP tool wrappers — one per read-only palace command (T11).

Each tool is a pure async function that takes a JSON-decoded ``arguments``
dict and returns a text payload. Tools NEVER import from ``palace.cli`` to
keep them decoupled from Typer/Rich.
"""

from __future__ import annotations

from palace.mcp.protocol import MCPTool
from palace.mcp.tools import (
    deps as _deps,
    explain as _explain,
    impact as _impact,
    plan as _plan,
    search as _search,
    symbols as _symbols,
)

TOOLS: list[MCPTool] = [
    MCPTool(
        name="palace_plan",
        description="Generate a structural change plan for a natural language task.",
        input_schema=_plan.INPUT_SCHEMA,
        handler=_plan.run,
    ),
    MCPTool(
        name="palace_explain",
        description="Explain a file or directory in natural language.",
        input_schema=_explain.INPUT_SCHEMA,
        handler=_explain.run,
    ),
    MCPTool(
        name="palace_impact",
        description="Analyze the blast radius of a file or symbol.",
        input_schema=_impact.INPUT_SCHEMA,
        handler=_impact.run,
    ),
    MCPTool(
        name="palace_search",
        description="Semantic code search.",
        input_schema=_search.INPUT_SCHEMA,
        handler=_search.run,
    ),
    MCPTool(
        name="palace_deps",
        description="Query file and symbol dependencies.",
        input_schema=_deps.INPUT_SCHEMA,
        handler=_deps.run,
    ),
    MCPTool(
        name="palace_symbols",
        description="List and filter indexed symbols.",
        input_schema=_symbols.INPUT_SCHEMA,
        handler=_symbols.run,
    ),
]
