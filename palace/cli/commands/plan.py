"""palace plan — Generate a structural change plan."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from palace.core.config import PalaceConfig
from palace.core.palace import Palace
from palace.graph.planner import PlanResult, StructuralPlanner

console = Console()


def plan_command(
    task: str = typer.Argument(
        ...,
        help="Natural language description of what you want to do.",
    ),
    scope: Optional[str] = typer.Option(  # noqa: UP007
        None,
        "--scope",
        "-s",
        help="Limit analysis to paths matching this glob.",
    ),
    format: str = typer.Option(
        "rich",
        "--format",
        help="Output format: rich, json, markdown.",
    ),
) -> None:
    """Generate a structural change plan from a task description."""
    # Discover palace config — walk up from cwd
    config = PalaceConfig.discover(path=Path.cwd())
    if config is None:
        console.print(
            "[bold red]Error:[/bold red] No palace found."
            " Run [cyan]palace init[/cyan] first."
        )
        raise typer.Exit(1)

    palace = Palace(config)
    palace.open()

    try:
        assert palace.store is not None
        result = StructuralPlanner(palace.store).plan(task, scope=scope)
    finally:
        palace.close()

    # --- Output routing ---
    if format == "json":
        _output_json(result)
    elif format == "markdown":
        _output_markdown(result)
    else:
        _output_rich(result)


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------


def _output_rich(result: PlanResult) -> None:
    """Render the plan with Rich markup."""
    console.print()
    console.print(
        Panel(
            f'[bold cyan]Structural Change Plan:[/bold cyan] [white]"{result.task}"[/white]',
            expand=False,
            border_style="cyan",
        )
    )

    # Keywords
    if result.keywords:
        kw_str = ", ".join(result.keywords)
        console.print(f"\n  [bold]Keywords:[/bold] {kw_str}")

    # No matches
    if not result.matched_files:
        console.print(
            "\n  [yellow]No matching files found.[/yellow]"
            " Try a more specific task description."
        )
        console.print(
            "\n  [dim]Note: Structural analysis only. Use an API key for"
            "\n  AI-powered change plans with rationale.[/dim]"
        )
        return

    # Detected patterns
    if result.patterns:
        console.print()
        for pat in result.patterns:
            console.print(f"  [bold green]Pattern detected:[/bold green] {pat.name}")
            console.print(f"    Directory: {pat.directory}")
            if pat.examples:
                console.print(f"    Examples: {', '.join(pat.examples)}")

    # Files in dependency order
    console.print("\n  [bold]Files likely involved (by dependency order):[/bold]\n")
    for idx, mf in enumerate(result.matched_files, start=1):
        sym_names = ", ".join(s["name"] for s in mf.matched_symbols[:5])
        score_str = f"[score: {mf.relevance_score}]"
        console.print(f"   {idx}. [cyan]{mf.path}[/cyan]  [dim]{score_str}[/dim]")
        if sym_names:
            console.print(f"      Matched: {sym_names}")
        if mf.reason:
            console.print(f"      Reason: {mf.reason}")

    # Test suggestions
    if result.suggested_tests:
        console.print("\n  [bold]Related tests:[/bold]")
        for t in result.suggested_tests:
            console.print(f"      {t}")

    console.print(
        "\n  [dim]Note: Structural analysis only. Use an API key for"
        "\n  AI-powered change plans with rationale.[/dim]\n"
    )


def _output_json(result: PlanResult) -> None:
    """Serialise PlanResult to JSON and print to stdout."""
    data = {
        "task": result.task,
        "keywords": result.keywords,
        "matched_files": [
            {
                "file_id": mf.file_id,
                "path": mf.path,
                "language": mf.language,
                "relevance_score": mf.relevance_score,
                "reason": mf.reason,
                "matched_symbols": [
                    {
                        "name": s.get("name"),
                        "kind": s.get("kind"),
                        "line_start": s.get("line_start"),
                    }
                    for s in mf.matched_symbols
                ],
            }
            for mf in result.matched_files
        ],
        "patterns": [
            {
                "name": p.name,
                "directory": p.directory,
                "examples": p.examples,
                "description": p.description,
            }
            for p in result.patterns
        ],
        "suggested_tests": result.suggested_tests,
    }
    typer.echo(json.dumps(data, indent=2))


def _output_markdown(result: PlanResult) -> None:
    """Render the plan as Markdown."""
    lines: list[str] = []
    lines.append(f'# Structural Change Plan: "{result.task}"')
    lines.append("")

    if result.keywords:
        lines.append(f"**Keywords:** {', '.join(result.keywords)}")
        lines.append("")

    if not result.matched_files:
        lines.append(
            "_No matching files found. Try a more specific task description._"
        )
        lines.append("")
        lines.append(
            "> Note: Structural analysis only."
            " Use an API key for AI-powered change plans with rationale."
        )
        typer.echo("\n".join(lines))
        return

    if result.patterns:
        lines.append("## Detected Patterns")
        lines.append("")
        for pat in result.patterns:
            lines.append(f"### {pat.name}")
            lines.append(f"- **Directory:** `{pat.directory}`")
            if pat.examples:
                lines.append(f"- **Examples:** {', '.join(pat.examples)}")
            lines.append("")

    lines.append("## Files Likely Involved (by dependency order)")
    lines.append("")
    for idx, mf in enumerate(result.matched_files, start=1):
        lines.append(f"{idx}. `{mf.path}` — score: {mf.relevance_score}")
        sym_names = ", ".join(s["name"] for s in mf.matched_symbols[:5])
        if sym_names:
            lines.append(f"   - Matched symbols: {sym_names}")
        if mf.reason:
            lines.append(f"   - Reason: {mf.reason}")

    if result.suggested_tests:
        lines.append("")
        lines.append("## Related Tests")
        lines.append("")
        for t in result.suggested_tests:
            lines.append(f"- `{t}`")

    lines.append("")
    lines.append(
        "> Note: Structural analysis only."
        " Use an API key for AI-powered change plans with rationale."
    )
    typer.echo("\n".join(lines))
