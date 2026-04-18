"""CLI wiring smoke tests (T12).

Verify that every command added in Phase 3 — explain, onboard, serve —
is registered with the Typer app and shows up in `palace --help`.
"""

from __future__ import annotations

from typer.testing import CliRunner

from palace.cli.main import app

runner = CliRunner()


def test_help_lists_all_phase3_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    out = result.stdout
    for name in ("init", "plan", "explain", "onboard", "serve", "impact", "search"):
        assert name in out, f"command `{name}` missing from help output"


def test_explain_help_mentions_no_llm() -> None:
    result = runner.invoke(app, ["explain", "--help"])
    assert result.exit_code == 0
    assert "--no-llm" in result.stdout
    assert "--provider" in result.stdout


def test_onboard_help_mentions_output() -> None:
    result = runner.invoke(app, ["onboard", "--help"])
    assert result.exit_code == 0
    assert "--output" in result.stdout
    assert "--no-llm" in result.stdout


def test_serve_help_renders() -> None:
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
