"""palace deps — Query file and symbol dependencies."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from palace.core.config import PalaceConfig
from palace.core.palace import Palace
from palace.graph.traversal import get_dependency_tree

console = Console()


def deps_command(
    target: str = typer.Argument(
        ...,
        help="File path to query dependencies for.",
    ),
    direction: str = typer.Option(
        "out",
        "--direction",
        "-d",
        help="Direction: in (dependents), out (dependencies), both.",
    ),
    transitive: bool = typer.Option(
        False,
        "--transitive",
        "-t",
        help="Follow transitive dependencies.",
    ),
    depth: int = typer.Option(
        10,
        "--depth",
        help="Max depth for transitive queries.",
    ),
    format: str = typer.Option(
        "tree",
        "--format",
        help="Output format: tree, table, json, dot.",
    ),
) -> None:
    """Query file and symbol dependencies."""
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
        _run_deps(
            palace=palace,
            target=target,
            direction=direction,
            transitive=transitive,
            depth=depth,
            format=format,
        )
    finally:
        palace.close()


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _resolve_target(palace: Palace, target: str) -> dict | None:
    """Find the file record matching target path.

    Tries exact match, then match relative to config.root, then basename match.
    """
    assert palace.store is not None
    root = palace.config.root

    # Normalise the target path
    target_path = Path(target)

    # 1. Exact match against stored path
    row = palace.store.get_file_by_path(target)
    if row is not None:
        return row

    # 2. Resolve relative to config.root and try again
    if not target_path.is_absolute():
        candidate = str(root / target_path)
        row = palace.store.get_file_by_path(candidate)
        if row is not None:
            return row

    # 3. Scan all files and match by suffix (path ends-with)
    all_files = palace.store.get_all_files()
    suffix = target.lstrip("/")
    for f in all_files:
        if f["path"].endswith(suffix):
            return f

    return None


def _run_deps(
    palace: Palace,
    target: str,
    direction: str,
    transitive: bool,
    depth: int,
    format: str,
) -> None:
    """Resolve target, query deps, and render the result."""
    assert palace.store is not None

    file_row = _resolve_target(palace, target)
    if file_row is None:
        console.print(
            f"[red]Error:[/red] File [bold]{target}[/bold] not found in the index.\n"
            "Tip: run [bold]palace init[/bold] to (re-)index the codebase."
        )
        raise typer.Exit(1)

    file_id: int = file_row["file_id"]
    root = str(palace.config.root)

    # Collect dependencies per direction
    out_deps: list[dict] = []
    in_deps: list[dict] = []

    if direction in ("out", "both"):
        out_deps = palace.store.get_dependencies(file_id, transitive=transitive)

    if direction in ("in", "both"):
        in_deps = palace.store.get_dependents(file_id, transitive=transitive)

    all_deps = out_deps + in_deps
    direct_count = len(all_deps)

    # For summary: count transitive uniquely
    trans_count = len({d["file_id"] for d in all_deps}) if transitive else direct_count

    _render_deps(
        palace=palace,
        file_row=file_row,
        out_deps=out_deps,
        in_deps=in_deps,
        direction=direction,
        transitive=transitive,
        depth=depth,
        format=format,
        direct_count=direct_count,
        trans_count=trans_count,
        root=root,
    )


def _short_path(path: str, root: str) -> str:
    """Strip root prefix from path for display."""
    if path.startswith(root + "/"):
        return path[len(root) + 1:]
    return path


def _render_deps(
    palace: Palace,
    file_row: dict,
    out_deps: list[dict],
    in_deps: list[dict],
    direction: str,
    transitive: bool,
    depth: int,
    format: str,
    direct_count: int,
    trans_count: int,
    root: str,
) -> None:
    """Render dependency results in the requested format."""
    target_short = _short_path(file_row["path"], root)

    if format == "json":
        payload: dict = {
            "file": file_row["path"],
            "direction": direction,
            "transitive": transitive,
        }
        if direction in ("out", "both"):
            payload["dependencies"] = [
                {k: (str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v)
                 for k, v in d.items()}
                for d in out_deps
            ]
        if direction in ("in", "both"):
            payload["dependents"] = [
                {k: (str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v)
                 for k, v in d.items()}
                for d in in_deps
            ]
        # Use typer.echo to avoid Rich wrapping long lines in the JSON output
        typer.echo(json.dumps(payload, indent=2))
        return

    if format == "dot":
        _render_dot(file_row, out_deps, in_deps, direction, root)
        return

    if format == "table":
        _render_table(
            target_short, out_deps, in_deps, direction, root, direct_count, trans_count
        )
        return

    # Default: tree
    _render_tree_format(
        palace=palace,
        file_row=file_row,
        out_deps=out_deps,
        in_deps=in_deps,
        direction=direction,
        transitive=transitive,
        depth=depth,
        root=root,
        direct_count=direct_count,
        trans_count=trans_count,
        target_short=target_short,
    )


def _render_tree_format(
    palace: Palace,
    file_row: dict,
    out_deps: list[dict],
    in_deps: list[dict],
    direction: str,
    transitive: bool,
    depth: int,
    root: str,
    direct_count: int,
    trans_count: int,
    target_short: str,
) -> None:
    """Render dependencies as a Rich tree hierarchy."""
    assert palace.store is not None

    summary = f"[bold]{target_short}[/bold]"
    tree = Tree(summary)

    if direction in ("out", "both") and out_deps:
        dep_label = "[bold blue]dependencies (out)[/bold blue]"
        if direction == "both":
            out_branch = tree.add(dep_label)
        else:
            out_branch = tree

        if transitive:
            # Use get_dependency_tree for nested view
            dep_tree = get_dependency_tree(palace.store, file_row["file_id"], max_depth=depth)
            visited: set[int] = set()
            _add_tree_children(out_branch, dep_tree["children"], root, visited)
        else:
            for dep in out_deps:
                short = _short_path(dep["path"], root)
                out_branch.add(f"[green]{short}[/green]  [dim]{dep['language']}[/dim]")

    if direction in ("in", "both") and in_deps:
        dep_label = "[bold yellow]dependents (in)[/bold yellow]"
        if direction == "both":
            in_branch = tree.add(dep_label)
        else:
            in_branch = tree

        for dep in in_deps:
            short = _short_path(dep["path"], root)
            depth_info = f"  [dim]depth={dep.get('depth', 1)}[/dim]" if transitive else ""
            in_branch.add(f"[yellow]{short}[/yellow]  [dim]{dep['language']}[/dim]{depth_info}")

    if not out_deps and not in_deps:
        tree.add("[dim]No dependencies found.[/dim]")

    console.print(tree)
    _print_summary(direct_count, trans_count, transitive)


def _add_tree_children(
    branch: Tree,
    children: list[dict],
    root: str,
    visited: set[int],
) -> None:
    """Recursively add child nodes to a Rich Tree, marking cycles."""
    for child in children:
        fid = child["file_id"]
        short = _short_path(child["path"], root)
        if fid in visited:
            branch.add(f"[red]{short}[/red]  [dim][cycle][/dim]")
            continue
        visited.add(fid)
        child_branch = branch.add(f"[green]{short}[/green]  [dim]{child['language']}[/dim]")
        if child.get("children"):
            _add_tree_children(child_branch, child["children"], root, visited)


def _render_table(
    target_short: str,
    out_deps: list[dict],
    in_deps: list[dict],
    direction: str,
    root: str,
    direct_count: int,
    trans_count: int,
) -> None:
    """Render dependencies as a Rich table."""
    console.print(f"[bold]Dependencies for:[/bold] [cyan]{target_short}[/cyan]")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Path", style="bold")
    table.add_column("Direction", style="green", no_wrap=True)
    table.add_column("Language", style="dim")
    table.add_column("Depth", justify="right")

    for dep in out_deps:
        short = _short_path(dep["path"], root)
        table.add_row(short, "out", dep.get("language", ""), str(dep.get("depth", 1)))

    for dep in in_deps:
        short = _short_path(dep["path"], root)
        table.add_row(short, "in", dep.get("language", ""), str(dep.get("depth", 1)))

    console.print(table)
    _print_summary(direct_count, trans_count, bool(out_deps or in_deps))


def _render_dot(
    file_row: dict,
    out_deps: list[dict],
    in_deps: list[dict],
    direction: str,
    root: str,
) -> None:
    """Render dependencies in DOT format for Graphviz."""
    lines: list[str] = ["digraph dependencies {", "  rankdir=LR;"]

    source = _short_path(file_row["path"], root)

    for dep in out_deps:
        short = _short_path(dep["path"], root)
        lines.append(f'  "{source}" -> "{short}";')

    for dep in in_deps:
        short = _short_path(dep["path"], root)
        lines.append(f'  "{short}" -> "{source}";')

    lines.append("}")
    typer.echo("\n".join(lines))


def _print_summary(direct_count: int, trans_count: int, transitive: bool) -> None:
    """Print the summary line at the bottom."""
    if transitive:
        console.print(
            f"\n[dim]Direct: {direct_count} files | Transitive: {trans_count} files[/dim]"
        )
    else:
        console.print(f"\n[dim]Direct: {direct_count} files[/dim]")
