"""palace search — Semantic code search using local embeddings."""

from __future__ import annotations

import json
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from palace.core.config import PalaceConfig
from palace.core.palace import Palace
from palace.semantic.embeddings import MockEmbeddingEngine
from palace.semantic.search import SemanticSearch

console = Console()


def search_command(
    query: str = typer.Argument(
        ...,
        help="Natural language search query.",
    ),
    kind: Optional[str] = typer.Option(  # noqa: UP007
        None,
        "--kind",
        "-k",
        help="Filter by symbol kind: function, class, method.",
    ),
    limit: int = typer.Option(
        20,
        "--limit",
        "-n",
        help="Maximum number of results.",
    ),
    format: str = typer.Option(
        "table",
        "--format",
        help="Output format: table, json.",
    ),
) -> None:
    """Semantic code search using local embeddings."""
    config = PalaceConfig.discover()
    if config is None:
        console.print(
            "[red]Error:[/red] No palace found in this directory or any parent.\n"
            "Run [bold]palace init[/bold] first."
        )
        raise typer.Exit(1)

    palace = Palace(config)
    palace.open()
    try:
        engine = MockEmbeddingEngine()
        searcher = SemanticSearch(palace.vector_store, engine)

        if not searcher.available():
            console.print(
                "[yellow]Embeddings not computed.[/yellow]\n"
                "Run [bold]palace init[/bold] to index embeddings."
            )
            raise typer.Exit(1)

        results = searcher.search(query, limit=limit, kind=kind)

        if not results:
            console.print(f"[dim]No results for:[/dim] {query}")
            return

        root = str(palace.config.root)
        _render(results, query, format, root)
    finally:
        palace.close()


def _render(results: list[dict], query: str, format: str, root: str) -> None:
    """Render search results."""
    if format == "json":
        clean = []
        for r in results:
            row = dict(r)
            for k, v in row.items():
                if not isinstance(v, (str, int, float, bool, type(None))):
                    row[k] = str(v)
            clean.append(row)
        typer.echo(json.dumps(clean, indent=2))
        return

    # Default: table
    console.print(f"[bold]Search:[/bold] \"{query}\"  ({len(results)} results)\n")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Score", justify="right", style="cyan", no_wrap=True)
    table.add_column("Kind", style="green", no_wrap=True)
    table.add_column("Name", style="bold")
    table.add_column("File", style="dim")

    for r in results:
        score = f"{r.get('score', 0):.2f}"
        kind_str = r.get("kind", "")
        name = r.get("name", r.get("path", ""))
        file_path = r.get("file_path", r.get("path", ""))
        if file_path.startswith(root + "/"):
            file_path = file_path[len(root) + 1:]
        table.add_row(score, kind_str, name, file_path)

    console.print(table)
