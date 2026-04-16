"""palace symbols — List and search symbols."""

from __future__ import annotations

import fnmatch
import json
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from palace.core.config import PalaceConfig
from palace.core.palace import Palace

console = Console()


def symbols_command(
    kind: Optional[str] = typer.Option(  # noqa: UP007
        None,
        "--kind",
        "-k",
        help="Filter by symbol kind: function, class, method, interface, etc.",
    ),
    file: Optional[str] = typer.Option(  # noqa: UP007
        None,
        "--file",
        "-f",
        help="Filter by file path (glob supported).",
    ),
    pattern: Optional[str] = typer.Option(  # noqa: UP007
        None,
        "--pattern",
        "-p",
        help="Filter by name (SQL LIKE syntax: % and _ wildcards).",
    ),
    exported_only: bool = typer.Option(
        False,
        "--exported-only",
        help="Show only exported symbols.",
    ),
    format: str = typer.Option(
        "table",
        "--format",
        help="Output format: table, json, tree.",
    ),
    limit: int = typer.Option(
        50,
        "--limit",
        "-n",
        help="Maximum number of results.",
    ),
) -> None:
    """List and search symbols in the indexed codebase."""
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
        _run_symbols(
            palace=palace,
            kind=kind,
            file=file,
            pattern=pattern,
            exported_only=exported_only,
            format=format,
            limit=limit,
        )
    finally:
        palace.close()


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _run_symbols(
    palace: Palace,
    kind: str | None,
    file: str | None,
    pattern: str | None,
    exported_only: bool,
    format: str,
    limit: int,
) -> None:
    """Query symbols from the store and render the results."""
    assert palace.store is not None

    # Resolve --file to file_id via glob match against stored paths
    file_id: int | None = None
    if file is not None:
        all_files = palace.store.get_all_files()
        # Support glob patterns: match against the stored relative-like paths
        matched = [f for f in all_files if fnmatch.fnmatch(f["path"], file)]
        if not matched:
            # Try matching with config.root prepended
            root_str = str(palace.config.root)
            matched = [
                f
                for f in all_files
                if fnmatch.fnmatch(f["path"], f"{root_str}/{file}")
            ]
        if not matched:
            console.print(f"[red]Error:[/red] No file matching [bold]{file}[/bold] found.")
            raise typer.Exit(1)
        # When multiple files match (glob), we need multiple file_ids — handled below
        if len(matched) == 1:
            file_id = matched[0]["file_id"]

    # Wrap pattern for contains-matching: "foo" → "%foo%"
    name_pattern: str | None = None
    if pattern is not None:
        # Only auto-wrap if the user didn't provide explicit wildcards
        if "%" not in pattern and "_" not in pattern:
            name_pattern = f"%{pattern}%"
        else:
            name_pattern = pattern

    # Query — single file_id or no file filter
    if file is not None and len(_get_matched_files(palace, file)) > 1:
        # Multiple files matched the glob: query each and merge
        symbols: list[dict] = []
        for f in _get_matched_files(palace, file):
            symbols.extend(
                palace.store.get_symbols(
                    file_id=f["file_id"],
                    kind=kind,
                    name_pattern=name_pattern,
                )
            )
    else:
        symbols = palace.store.get_symbols(
            file_id=file_id,
            kind=kind,
            name_pattern=name_pattern,
        )

    # Post-filter: exported_only
    if exported_only:
        symbols = [s for s in symbols if s.get("is_exported")]

    total = len(symbols)
    symbols = symbols[:limit]

    _render_symbols(symbols, total, limit, format, palace)


def _get_matched_files(palace: Palace, file_pattern: str) -> list[dict]:
    """Return all file records whose stored path matches the glob pattern."""
    assert palace.store is not None
    all_files = palace.store.get_all_files()
    matched = [f for f in all_files if fnmatch.fnmatch(f["path"], file_pattern)]
    if not matched:
        root_str = str(palace.config.root)
        matched = [
            f
            for f in all_files
            if fnmatch.fnmatch(f["path"], f"{root_str}/{file_pattern}")
        ]
    return matched


def _file_path_for_id(palace: Palace, file_id: int) -> str:
    """Return the path string for a given file_id."""
    assert palace.store is not None
    for f in palace.store.get_all_files():
        if f["file_id"] == file_id:
            return f["path"]
    return str(file_id)


def _short_path(path: str, root: str) -> str:
    """Strip root prefix from path for display."""
    if path.startswith(root + "/"):
        return path[len(root) + 1:]
    return path


def _render_symbols(
    symbols: list[dict],
    total: int,
    limit: int,
    format: str,
    palace: Palace,
) -> None:
    """Render symbol results in the requested format."""
    showing = len(symbols)
    root = str(palace.config.root)

    if format == "json":
        # Produce clean JSON — replace non-serialisable values
        clean = []
        for s in symbols:
            row = dict(s)
            # indexed_at and similar Timestamp objects → str
            for k, v in row.items():
                if not isinstance(v, (str, int, float, bool, type(None))):
                    row[k] = str(v)
            clean.append(row)
        # Use typer.echo to avoid Rich wrapping long lines in the JSON output
        typer.echo(json.dumps(clean, indent=2))
        return

    if format == "tree":
        _render_symbols_tree(symbols, total, showing, root, palace)
        return

    # Default: table
    console.print(
        f"[bold]Symbols[/bold] — [cyan]{total}[/cyan] results "
        f"(showing [cyan]{showing}[/cyan])"
    )
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Kind", style="green", no_wrap=True)
    table.add_column("Name", style="bold")
    table.add_column("File", style="dim")
    table.add_column("Line", justify="right")
    table.add_column("Signature", style="dim")

    for sym in symbols:
        file_path = _file_path_for_id(palace, sym["file_id"])
        short = _short_path(file_path, root)
        sig = sym.get("signature") or ""
        table.add_row(
            sym["kind"],
            sym["name"],
            short,
            str(sym["line_start"]),
            sig,
        )

    console.print(table)


def _render_symbols_tree(
    symbols: list[dict],
    total: int,
    showing: int,
    root: str,
    palace: Palace,
) -> None:
    """Render symbols grouped by file as a Rich tree."""
    console.print(
        f"[bold]Symbols[/bold] — [cyan]{total}[/cyan] results "
        f"(showing [cyan]{showing}[/cyan])"
    )

    # Group by file_id → path
    by_file: dict[int, list[dict]] = {}
    for sym in symbols:
        fid = sym["file_id"]
        by_file.setdefault(fid, []).append(sym)

    tree = Tree("[bold]codebase[/bold]")
    for fid, file_syms in by_file.items():
        file_path = _file_path_for_id(palace, fid)
        short = _short_path(file_path, root)
        branch = tree.add(f"[blue]{short}[/blue]")
        for sym in file_syms:
            sig = sym.get("signature") or ""
            label = f"[green]{sym['kind']}[/green] [bold]{sym['name']}[/bold]"
            if sig:
                label += f"  [dim]{sig}[/dim]"
            branch.add(label)

    console.print(tree)
