"""palace explore — launch the interactive TUI explorer."""

from __future__ import annotations

import typer
from rich.console import Console

from palace.core.config import PalaceConfig
from palace.core.palace import Palace

console = Console()


def explore_command() -> None:
    """Launch the interactive TUI explorer."""
    config = PalaceConfig.discover()
    if config is None:
        console.print("[red]Error:[/red] No palace found. Run palace init first.")
        raise typer.Exit(1)

    palace = Palace(config)
    palace.open()
    try:
        from palace.cli.ui.app import PalaceApp

        app = PalaceApp(palace)
        app.run()
    finally:
        palace.close()
