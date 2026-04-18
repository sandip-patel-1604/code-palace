"""MCP stdio server for Code Palace."""

from __future__ import annotations

from typing import Any

from palace.core.exceptions import MCPError
from palace.core.logging import get_logger
from palace.mcp.protocol import MCPTool, redact_secrets, truncate_content

logger = get_logger(__name__)


def _import_mcp() -> tuple[Any, Any, Any]:
    """Lazily import the MCP SDK modules.

    Returns:
        A 3-tuple of ``(mcp.server, mcp.server.stdio, mcp.types)``.

    Raises:
        MCPError: If the ``mcp`` package is not installed.
    """
    try:
        import mcp.server as _server
        import mcp.server.stdio as _stdio
        import mcp.types as _types

        return _server, _stdio, _types
    except ImportError as exc:
        raise MCPError(
            "mcp SDK not installed — pip install mcp>=1.2"
        ) from exc


class PalaceMCPServer:
    """MCP server that exposes Code Palace tools over stdio transport.

    Parameters:
        tools: List of :class:`~palace.mcp.protocol.MCPTool` instances to
            register.  Defaults to an empty list; tools are typically
            supplied by T11.
    """

    def __init__(self, tools: list[MCPTool] | None = None) -> None:
        self._tools: list[MCPTool] = tools if tools is not None else []

    async def run(self) -> None:
        """Start the MCP stdio server and block until the client disconnects."""
        mcp_server, mcp_stdio, mcp_types = _import_mcp()

        server = mcp_server.Server("palace")

        # Build a name→tool mapping for fast lookup during call dispatch.
        tool_map: dict[str, MCPTool] = {t.name: t for t in self._tools}

        @server.list_tools()
        async def list_tools() -> list[mcp_types.Tool]:
            return [
                mcp_types.Tool(
                    name=t.name,
                    description=t.description,
                    inputSchema=t.input_schema,
                )
                for t in self._tools
            ]

        @server.call_tool()
        async def call_tool(
            name: str, arguments: dict
        ) -> list[mcp_types.TextContent]:
            tool = tool_map.get(name)
            if tool is None:
                return [
                    mcp_types.TextContent(
                        type="text",
                        text=f"Unknown tool: {name}",
                    )
                ]
            try:
                result = await tool.handler(arguments)
                return [
                    mcp_types.TextContent(
                        type="text",
                        text=truncate_content(result),
                    )
                ]
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Tool %s failed: %s",
                    name,
                    redact_secrets({"tool": name, "args": arguments}),
                )
                return [
                    mcp_types.TextContent(
                        type="text",
                        text=str(exc),
                    )
                ]

        async with mcp_stdio.stdio_server() as (read_stream, write_stream):
            init_options = server.create_initialization_options()
            await server.run(read_stream, write_stream, init_options)


async def main() -> None:
    """Entry point: load tools from T11 and run the server."""
    tools: list[MCPTool] = []
    try:
        from palace.mcp.tools import TOOLS  # type: ignore[import]

        tools = TOOLS
    except (ImportError, AttributeError):
        pass

    await PalaceMCPServer(tools).run()
