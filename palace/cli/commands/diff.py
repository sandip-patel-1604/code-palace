"""palace diff — Git diff impact analysis for a commit range."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from palace.core.config import PalaceConfig
from palace.core.palace import Palace
from palace.graph.impact import ImpactAnalyzer, ImpactResult

console = Console()


def diff_command(
    range: str = typer.Argument(
        "HEAD~1..HEAD",
        help="Git diff range.",
    ),
    format: str = typer.Option(
        "rich",
        "--format",
        help="Output: rich, json.",
    ),
) -> None:
    """Impact analysis on a git diff range."""
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
        changed_paths = _get_changed_files(range, config.root)
        if changed_paths is None:
            # subprocess failed — not a git repo or bad range
            raise typer.Exit(1)

        if not changed_paths:
            console.print("No changes in range")
            return

        results = _analyze_changed_files(palace, changed_paths)

        if format == "json":
            _render_json(range, changed_paths, results)
        else:
            _render_rich(range, changed_paths, results, palace)
    finally:
        palace.close()


# ------------------------------------------------------------------
# Git helpers
# ------------------------------------------------------------------


def _get_changed_files(range: str, root: Path) -> list[str] | None:
    """Run git diff --name-only and return the list of changed file paths.

    Returns None when git is unavailable or the range is invalid, so the
    caller can distinguish "no diff" (empty list) from "git error" (None).
    """
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", range],
            capture_output=True,
            text=True,
            cwd=str(root),
        )
    except FileNotFoundError:
        console.print("[red]Error:[/red] git not found.  Install git and try again.")
        return None

    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        console.print(f"[red]Error:[/red] git diff failed: {stderr or 'unknown error'}")
        return None

    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    return lines


# ------------------------------------------------------------------
# Analysis helpers
# ------------------------------------------------------------------


def _analyze_changed_files(
    palace: Palace,
    changed_paths: list[str],
) -> list[ImpactResult]:
    """Look up each changed path in the store and run impact analysis.

    Files not present in the index are silently skipped — they may be
    untracked assets, deleted files, or belong to a language not indexed.
    """
    assert palace.store is not None
    analyzer = ImpactAnalyzer(palace.store)
    root = str(palace.config.root)
    results: list[ImpactResult] = []

    for rel_path in changed_paths:
        file_row = _resolve_path(palace, rel_path, root)
        if file_row is None:
            continue
        result = analyzer.analyze_file(file_row["file_id"])
        results.append(result)

    return results


def _resolve_path(palace: Palace, rel_path: str, root: str) -> dict | None:
    """Try relative then absolute path lookup against the store index.

    The store may record paths as absolute strings rooted at the project
    directory, so we attempt both the raw relative path and the
    root-prefixed absolute form.
    """
    assert palace.store is not None

    row = palace.store.get_file_by_path(rel_path)
    if row is not None:
        return row

    abs_candidate = str(Path(root) / rel_path)
    row = palace.store.get_file_by_path(abs_candidate)
    if row is not None:
        return row

    # Last resort: suffix match across all indexed files
    suffix = rel_path.lstrip("/")
    for f in palace.store.get_all_files():
        if f["path"].endswith(suffix):
            return f

    return None


# ------------------------------------------------------------------
# Aggregation
# ------------------------------------------------------------------


def _aggregate(results: list[ImpactResult]) -> tuple[list[dict], int, str, list[str]]:
    """Aggregate per-file impact results into summary metrics.

    Returns (domains_affected, total_transitive, overall_risk, suggested_tests).
    overall_risk is the maximum risk level across all analyzed files.
    """
    _risk_order = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}

    domain_counts: dict[str, int] = {}
    total_transitive = 0
    overall_risk = "LOW"
    seen_tests: set[str] = set()

    for r in results:
        total_transitive += r.transitive_dependents
        if _risk_order.get(r.risk, 0) > _risk_order.get(overall_risk, 0):
            overall_risk = r.risk
        for d in r.domain_impact:
            name = d["name"]
            domain_counts[name] = domain_counts.get(name, 0) + d.get("file_count", 0)
        for t in r.test_files:
            seen_tests.add(t)

    domains_affected = [
        {"name": n, "file_count": c}
        for n, c in sorted(domain_counts.items(), key=lambda x: -x[1])
    ]
    suggested_tests = sorted(seen_tests)
    return domains_affected, total_transitive, overall_risk, suggested_tests


# ------------------------------------------------------------------
# Rendering
# ------------------------------------------------------------------


def _render_rich(
    range: str,
    changed_paths: list[str],
    results: list[ImpactResult],
    palace: Palace,
) -> None:
    """Print a Rich panel with the diff impact summary."""
    root = str(palace.config.root)
    domains_affected, total_transitive, overall_risk, suggested_tests = _aggregate(results)

    # Build a fast lookup so we can annotate changed files with risk
    risk_by_path: dict[str, str] = {}
    for r in results:
        short = r.path
        if short.startswith(root + "/"):
            short = short[len(root) + 1:]
        risk_by_path[short] = r.risk
        # Also key by the raw relative path in case paths differ
        risk_by_path[r.path] = r.risk

    risk_color = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}

    lines: list[str] = [
        f"  [bold]Diff Impact:[/bold] {range} ({len(changed_paths)} files changed)\n",
        "  [bold]Changed Files:[/bold]",
    ]

    for i, p in enumerate(changed_paths, start=1):
        risk = risk_by_path.get(p) or risk_by_path.get(str(Path(root) / p))
        if risk:
            color = risk_color.get(risk, "dim")
            lines.append(f"    {i}. {p}  [[{color}]{risk}[/{color}]]")
        else:
            lines.append(f"    {i}. {p}  [dim](not indexed)[/dim]")

    if domains_affected:
        lines.append("")
        lines.append("  [bold]Domains Affected:[/bold]")
        domain_parts = ", ".join(
            f"{d['name']} ({d['file_count']} files)" for d in domains_affected
        )
        lines.append(f"    {domain_parts}")

    lines.append("")
    lines.append(f"  [bold]Blast Radius:[/bold]       {total_transitive} files transitively affected")

    overall_color = risk_color.get(overall_risk, "dim")
    lines.append(
        f"  [bold]Overall Risk:[/bold]       [{overall_color}]{overall_risk}[/{overall_color}]"
    )

    if suggested_tests:
        lines.append("")
        lines.append("  [bold]Suggested Tests:[/bold]")
        for t in suggested_tests[:10]:
            short_t = t
            if t.startswith(root + "/"):
                short_t = t[len(root) + 1:]
            lines.append(f"    {short_t}")

    console.print(Panel(
        "\n".join(lines),
        title="[bold]Diff Impact Analysis[/bold]",
        expand=False,
    ))


def _render_json(
    range: str,
    changed_paths: list[str],
    results: list[ImpactResult],
) -> None:
    """Emit diff impact as a JSON object."""
    domains_affected, total_transitive, overall_risk, suggested_tests = _aggregate(results)

    result_by_path: dict[str, ImpactResult] = {}
    for r in results:
        result_by_path[r.path] = r

    changed_files = []
    for p in changed_paths:
        # Try to match by suffix when absolute paths don't align
        matched: ImpactResult | None = result_by_path.get(p)
        if matched is None:
            for r in results:
                if r.path.endswith(p):
                    matched = r
                    break

        if matched:
            changed_files.append({
                "path": p,
                "risk": matched.risk,
                "direct_dependents": matched.direct_dependents,
                "transitive_dependents": matched.transitive_dependents,
            })
        else:
            changed_files.append({
                "path": p,
                "risk": None,
                "direct_dependents": None,
                "transitive_dependents": None,
            })

    data = {
        "range": range,
        "changed_files": changed_files,
        "domains_affected": domains_affected,
        "total_transitive": total_transitive,
        "overall_risk": overall_risk,
        "suggested_tests": suggested_tests,
    }
    typer.echo(json.dumps(data, indent=2))
