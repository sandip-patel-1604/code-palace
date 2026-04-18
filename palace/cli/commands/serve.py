"""palace serve — run the MCP stdio server (T12)."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console

from palace.core.exceptions import MCPError

console = Console()


def serve_command() -> None:
    """Run the palace MCP stdio server until the client disconnects."""
    from palace.mcp.server import main as mcp_main

    try:
        asyncio.run(mcp_main())
    except MCPError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(1) from exc
    except KeyboardInterrupt:
        raise typer.Exit(0)
