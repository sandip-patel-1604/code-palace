"""Palace CLI — the main entry point."""

from __future__ import annotations

import typer

from palace import __version__

app = typer.Typer(
    name="palace",
    help="Navigate any codebase like you built it.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"palace {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """Code Palace — Navigate any codebase like you built it."""


# Register commands
from palace.cli.commands.init import init_command  # noqa: E402
from palace.cli.commands.symbols import symbols_command  # noqa: E402
from palace.cli.commands.deps import deps_command  # noqa: E402
from palace.cli.commands.plan import plan_command  # noqa: E402

app.command(name="init", help="Parse and index a codebase.")(init_command)
app.command(name="symbols", help="List and search symbols.")(symbols_command)
app.command(name="deps", help="Query file and symbol dependencies.")(deps_command)
app.command(name="plan", help="Generate a structural change plan.")(plan_command)
