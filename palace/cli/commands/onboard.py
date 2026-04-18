"""palace onboard — auto-generated codebase tour (T9)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from palace.core.config import PalaceConfig
from palace.core.palace import Palace
from palace.graph.patterns import PatternDetector
from palace.llm.availability import check_availability, render_degraded_notice
from palace.llm.onboarder import Onboarder, OnboardContext

console = Console()


def onboard_command(
    output: Optional[Path] = typer.Option(  # noqa: UP007
        None,
        "--output",
        "-o",
        help="Write the tour to a file instead of stdout.",
    ),
    no_llm: bool = typer.Option(
        False,
        "--no-llm",
        help="Force structural output (skip LLM).",
    ),
    provider: Optional[str] = typer.Option(  # noqa: UP007
        None,
        "--provider",
        help="Force a specific LLM provider: claude, openai, or ollama.",
    ),
) -> None:
    """Generate an onboarding tour of the indexed codebase."""
    config = PalaceConfig.discover(path=Path.cwd())
    if config is None:
        console.print(
            "[bold red]Error:[/bold red] No palace found."
            " Run [cyan]palace init[/cyan] first."
        )
        raise typer.Exit(1)

    if output is not None and output.exists() and output.is_dir():
        console.print(
            f"[bold red]Error:[/bold red] `{output}` is a directory, not a file."
        )
        raise typer.Exit(1)

    palace = Palace(config)
    palace.open()

    try:
        assert palace.store is not None
        ctx = _build_context(palace)

        degraded = False
        provider_obj = None
        if not no_llm:
            availability = check_availability(prefer=provider)
            if availability.is_available:
                provider_obj = availability.provider
            else:
                degraded = True

        tour = Onboarder(provider_obj).generate(ctx)
    finally:
        palace.close()

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(tour.text, encoding="utf-8")
        console.print(f"[green]Wrote onboarding tour to[/green] `{output}`")
    else:
        typer.echo(tour.text)

    if degraded and not no_llm:
        render_degraded_notice(console, "palace onboard")


def _build_context(palace: Palace) -> OnboardContext:
    """Gather files, symbols, domains, entry points, concerns, patterns."""
    assert palace.store is not None
    store = palace.store

    all_files = store.get_all_files()
    symbols = store.get_symbols()

    # Domains with sample file paths
    domains: list[dict] = []
    try:
        for d in store.get_domains():
            files = store.get_domain_files(d["domain_id"])
            d["sample_files"] = [f["path"] for f in files[:10]]
            domains.append(d)
    except Exception:  # noqa: BLE001
        pass

    # Entry points: count inbound CALLS/IMPORTS edges per file
    try:
        edges = store.get_edges()
    except Exception:  # noqa: BLE001
        edges = []
    inbound: Counter[int] = Counter()
    for e in edges:
        # Edges reference symbols — approximate "most depended on files" by
        # counting edges whose target symbol belongs to each file.
        to_sym_id = e.get("to_symbol_id")
        if to_sym_id is None:
            continue
        # Look up symbol → file_id via the symbols list once.
    sym_to_file: dict[int, int] = {s["symbol_id"]: s["file_id"] for s in symbols}
    for e in edges:
        to_sym = e.get("to_symbol_id")
        if to_sym in sym_to_file:
            inbound[sym_to_file[to_sym]] += 1

    entry_points = []
    for file_id, count in inbound.most_common(20):
        row = store.get_file_by_id(file_id)
        if row is not None:
            row["dependent_count"] = count
            entry_points.append(row)

    # Patterns
    detector = PatternDetector(store)
    concerns = detector.detect_cross_cutting()
    # For naming conventions, detect across all files (no matched_files slice)
    patterns = detector.detect_naming_conventions(all_files, [])

    return OnboardContext(
        root=str(palace.config.root),
        file_count=len(all_files),
        symbol_count=len(symbols),
        domains=domains,
        entry_points=entry_points,
        concerns=concerns,
        patterns=patterns,
    )
