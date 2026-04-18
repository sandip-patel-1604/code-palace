"""palace explain — natural-language explanation of a file or directory (T8)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from palace.core.config import PalaceConfig
from palace.core.palace import Palace
from palace.core.resolve import resolve_file_target
from palace.graph.patterns import PatternDetector
from palace.llm.availability import check_availability, render_degraded_notice
from palace.llm.explainer import Explainer, ExplanationContext

console = Console()


def explain_command(
    target: str = typer.Argument(
        ...,
        help="File path or directory to explain (relative to project root).",
    ),
    format: str = typer.Option(
        "rich",
        "--format",
        help="Output format: rich or markdown.",
    ),
    no_llm: bool = typer.Option(
        False,
        "--no-llm",
        help="Force structural output (skip LLM even when a provider is available).",
    ),
    provider: Optional[str] = typer.Option(  # noqa: UP007
        None,
        "--provider",
        help="Force a specific LLM provider: claude, openai, or ollama.",
    ),
) -> None:
    """Produce a natural-language explanation of a file or directory."""
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
        ctx = _build_context(palace, target)
        if not ctx.files:
            console.print(
                f"[bold red]Error:[/bold red] `{target}` not found in the index.\n"
                f"Run [cyan]palace init[/cyan] to re-index, or check the path."
            )
            raise typer.Exit(1)

        degraded = False
        provider_obj = None
        if not no_llm:
            availability = check_availability(prefer=provider)
            if availability.is_available:
                provider_obj = availability.provider
            else:
                degraded = True

        explanation = Explainer(provider_obj).explain(ctx)
    finally:
        palace.close()

    if format == "markdown":
        typer.echo(explanation.text)
    else:
        console.print()
        console.print(explanation.text)

    if degraded and not no_llm:
        render_degraded_notice(console, "palace explain")


def _build_context(palace: Palace, target: str) -> ExplanationContext:
    """Collect files, symbols, and cross-cutting concerns for *target*."""
    assert palace.store is not None
    store = palace.store
    root = palace.config.root

    file_row = resolve_file_target(store, target, root)
    files: list[dict] = []
    if file_row is not None:
        files = [file_row]
    else:
        # Treat as directory prefix: find files whose path starts with target.
        target_norm = target.rstrip("/")
        for f in store.get_all_files():
            p = f["path"]
            if p == target_norm or p.startswith(target_norm + "/"):
                files.append(f)

    symbols: list[dict] = []
    for f in files:
        file_syms = store.get_symbols(file_id=f["file_id"])
        symbols.extend(file_syms)

    concerns = PatternDetector(store).detect_cross_cutting()

    return ExplanationContext(
        target=target, files=files, symbols=symbols, concerns=concerns
    )
