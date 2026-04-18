"""palace impact — Analyze blast radius of a file or symbol."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from palace.core.config import PalaceConfig
from palace.core.palace import Palace
from palace.graph.impact import ImpactAnalyzer

console = Console()


def impact_command(
    target: str = typer.Argument(
        ...,
        help="File path or file.py:SymbolName.",
    ),
    format: str = typer.Option(
        "rich",
        "--format",
        help="Output format: rich, json.",
    ),
    depth: int = typer.Option(
        10,
        "--depth",
        help="Max transitive depth.",
    ),
) -> None:
    """Analyze blast radius of a file or symbol."""
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

        # Parse target: "file.py:SymbolName" or just "file.py"
        symbol_name: str | None = None
        file_path = target
        if ":" in target:
            file_path, symbol_name = target.rsplit(":", 1)

        file_row = _resolve_target(palace, file_path)
        if file_row is None:
            console.print(
                f"[red]Error:[/red] File [bold]{file_path}[/bold] not found in the index.\n"
                "Tip: run [bold]palace init[/bold] to (re-)index the codebase."
            )
            raise typer.Exit(1)

        analyzer = ImpactAnalyzer(palace.store)
        file_id: int = file_row["file_id"]

        if symbol_name:
            result = analyzer.analyze_symbol(file_id, symbol_name)
            if result is None:
                console.print(f"[red]Error:[/red] Symbol [bold]{symbol_name}[/bold] not found in {file_path}.")
                raise typer.Exit(1)
        else:
            result = analyzer.analyze_file(file_id, depth=depth)

        if format == "json":
            _render_json(result)
        else:
            _render_rich(result, palace)
    finally:
        palace.close()


def _resolve_target(palace: Palace, target: str) -> dict | None:
    """Find the file record matching target path via shared resolver."""
    assert palace.store is not None
    from palace.core.resolve import resolve_file_target

    return resolve_file_target(palace.store, target, palace.config.root)


def _render_json(result: object) -> None:
    """Serialize ImpactResult to JSON."""
    from palace.graph.impact import ImpactResult

    assert isinstance(result, ImpactResult)
    data = {
        "file_id": result.file_id,
        "path": result.path,
        "direct_dependents": result.direct_dependents,
        "transitive_dependents": result.transitive_dependents,
        "risk": result.risk,
        "domain_impact": result.domain_impact,
        "cochange_partners": result.cochange_partners,
        "ownership": result.ownership,
        "churn": result.churn,
        "test_files": result.test_files,
    }
    typer.echo(json.dumps(data, indent=2, default=str))


def _render_rich(result: object, palace: Palace) -> None:
    """Render impact analysis with Rich."""
    from palace.graph.impact import ImpactResult

    assert isinstance(result, ImpactResult)
    root = str(palace.config.root)
    short_path = result.path
    if short_path.startswith(root + "/"):
        short_path = short_path[len(root) + 1:]

    risk_color = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}.get(result.risk, "dim")

    lines = [
        f"  [bold]File:[/bold]       {short_path}",
        f"  [bold]Risk:[/bold]       [{risk_color}]{result.risk}[/{risk_color}]",
        "",
        f"  Direct dependents:     [cyan]{result.direct_dependents}[/cyan]",
        f"  Transitive dependents: [cyan]{result.transitive_dependents}[/cyan]",
    ]

    if result.domain_impact:
        domains_str = ", ".join(
            f"{d['name']} ({d['file_count']})" for d in result.domain_impact
        )
        lines.append(f"  Domain impact:         {domains_str}")

    if result.ownership:
        top = result.ownership[0]
        lines.append(f"  Primary owner:         {top['author_name']} ({top['commit_count']} commits)")

    if result.churn:
        lines.append(f"  Churn (90d):           {result.churn['change_count']} changes")

    if result.test_files:
        lines.append(f"  Test files:            {len(result.test_files)}")
        for t in result.test_files[:5]:
            short_t = t
            if t.startswith(root + "/"):
                short_t = t[len(root) + 1:]
            lines.append(f"    {short_t}")

    console.print(Panel(
        "\n".join(lines),
        title="[bold]Impact Analysis[/bold]",
        expand=False,
    ))
