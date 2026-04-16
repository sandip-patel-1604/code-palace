"""palace domains — Show auto-discovered domain clusters."""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from palace.core.config import PalaceConfig
from palace.core.palace import Palace
from palace.graph.clustering import DomainClusterer

console = Console()


def domains_command(
    format: str = typer.Option(
        "tree",
        "--format",
        help="Output format: tree, table, json.",
    ),
    min_files: int = typer.Option(
        2,
        "--min-files",
        help="Minimum files per domain.",
    ),
    recompute: bool = typer.Option(
        False,
        "--recompute",
        help="Force re-clustering.",
    ),
) -> None:
    """Show auto-discovered domain clusters."""
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
        assert palace.store is not None
        existing = palace.store.get_domains()

        if recompute or not existing:
            clusterer = DomainClusterer(palace.store)
            domains = clusterer.cluster(min_files=min_files)
        else:
            domains = []
            for d in existing:
                files = palace.store.get_domain_files(d["domain_id"])
                domains.append({
                    "domain_id": d["domain_id"],
                    "name": d["name"],
                    "file_count": len(files),
                })

        if not domains:
            console.print("[yellow]No domains found.[/yellow] Run [bold]palace init[/bold] first.")
            return

        _render(domains, palace, format)
    finally:
        palace.close()


def _render(domains: list[dict], palace: Palace, format: str) -> None:
    """Render domains in the requested format."""
    assert palace.store is not None
    root_str = str(palace.config.root)

    if format == "json":
        payload = []
        for d in domains:
            files = palace.store.get_domain_files(d["domain_id"])
            payload.append({
                "domain_id": d["domain_id"],
                "name": d["name"],
                "file_count": d["file_count"],
                "files": [_short(f["path"], root_str) for f in files],
            })
        typer.echo(json.dumps(payload, indent=2))
        return

    if format == "table":
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Domain", style="bold")
        table.add_column("Files", justify="right")
        for d in domains:
            table.add_row(d["name"], str(d["file_count"]))
        console.print(table)
        return

    # Default: tree
    tree = Tree(f"[bold]Domain Map[/bold] ({len(domains)} domains)")
    for d in domains:
        files = palace.store.get_domain_files(d["domain_id"])
        branch = tree.add(f"[bold cyan]{d['name']}[/bold cyan]  [dim]({d['file_count']} files)[/dim]")
        for f in files[:10]:
            branch.add(f"[green]{_short(f['path'], root_str)}[/green]")
        if len(files) > 10:
            branch.add(f"[dim]... and {len(files) - 10} more[/dim]")
    console.print(tree)


def _short(path: str, root: str) -> str:
    if path.startswith(root + "/"):
        return path[len(root) + 1:]
    return path
