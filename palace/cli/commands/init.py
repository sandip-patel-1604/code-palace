"""palace init — Parse and index a codebase."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn
from rich.tree import Tree

from palace.core.config import PalaceConfig
from palace.core.palace import Palace

console = Console()


def init_command(
    path: Optional[Path] = typer.Argument(  # noqa: UP007
        None,
        help="Root directory to index. Defaults to current directory.",
    ),
    languages: Optional[str] = typer.Option(  # noqa: UP007
        None,
        "--languages",
        "-l",
        help="Comma-separated languages to parse (default: auto-detect).",
    ),
    exclude: Optional[str] = typer.Option(  # noqa: UP007
        None,
        "--exclude",
        "-e",
        help="Additional glob patterns to exclude (comma-separated).",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Re-index even if .palace/ exists.",
    ),
    no_progress: bool = typer.Option(
        False,
        "--no-progress",
        help="Disable progress bars.",
    ),
) -> None:
    """Parse and index a codebase into a Palace graph."""
    root = (path or Path.cwd()).resolve()

    if not root.exists():
        console.print(f"[red]Error:[/red] path does not exist: {root}")
        raise typer.Exit(1)

    if not root.is_dir():
        console.print(f"[red]Error:[/red] path is not a directory: {root}")
        raise typer.Exit(1)

    # Check for existing palace
    palace_dir = root / ".palace"
    if palace_dir.exists() and not force:
        console.print(
            f"[yellow]Warning:[/yellow] {root} already has a .palace/ directory.\n"
            "Use [bold]--force[/bold] to re-index."
        )
        raise typer.Exit(1)

    # Build language and exclude lists from CLI options
    lang_list: list[str] | None = None
    if languages:
        lang_list = [l.strip() for l in languages.split(",") if l.strip()]

    exclude_extra: list[str] = []
    if exclude:
        exclude_extra = [e.strip() for e in exclude.split(",") if e.strip()]

    # Initialise config (creates .palace/ and config.json)
    config = PalaceConfig.initialize(
        path=root,
        languages=lang_list or [],
        exclude_patterns=None,  # use defaults; will be updated after detection
    )
    if exclude_extra:
        config.exclude_patterns = config.exclude_patterns + exclude_extra
        config.save()

    palace = Palace(config)

    # Run with optional progress bar
    stats = _run_init(palace, force=force, no_progress=no_progress)

    # Detect language counts for the summary panel
    lang_counts = config.detect_languages()

    _print_summary(root, lang_counts, stats)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _run_init(
    palace: Palace,
    force: bool,
    no_progress: bool,
) -> object:
    """Run palace.init() with an optional Rich progress bar."""
    from palace.graph.builder import BuildStats

    if no_progress:
        return palace.init(force=force)

    with Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Parsing…", total=None)

        def _callback(done: int, total: int) -> None:
            progress.update(task, completed=done, total=total)

        stats = palace.init(force=force, progress_callback=_callback)

    return stats


def _print_summary(
    root: Path,
    lang_counts: dict[str, int],
    stats: object,
) -> None:
    """Render the post-init summary panel to the console."""
    from palace.graph.builder import BuildStats

    assert isinstance(stats, BuildStats)

    # Language line: "Python (847), TypeScript (203)"
    lang_str = ", ".join(
        f"{lang.capitalize()} ({count})" for lang, count in sorted(lang_counts.items())
    ) or "none detected"

    tree = Tree("[bold]Summary[/bold]")
    tree.add(f"Files:     [cyan]{stats.files}[/cyan]")
    tree.add(f"Symbols:   [cyan]{stats.symbols}[/cyan]")
    tree.add(f"Edges:     [cyan]{stats.edges}[/cyan]")
    tree.add(
        f"Imports:   [cyan]{stats.imports_total}[/cyan] "
        f"([green]{stats.imports_resolved} resolved[/green])"
    )
    tree.add(f"Duration:  [cyan]{stats.duration_seconds:.1f}s[/cyan]")

    panel_content = (
        f"  Root:       {root}\n"
        f"  Languages:  {lang_str}\n\n"
        f"{_render_tree(tree)}\n"
        f"  Palace ready [green]→[/green] .palace/"
    )

    console.print(
        Panel(
            panel_content,
            title="[bold green]Palace Init[/bold green]",
            expand=False,
        )
    )


def _render_tree(tree: Tree) -> str:
    """Capture a Rich Tree as a plain-text string for embedding in a Panel."""
    from io import StringIO

    from rich.console import Console as _Console

    buf = StringIO()
    _con = _Console(file=buf, highlight=False)
    _con.print(tree)
    return buf.getvalue().rstrip("\n")
