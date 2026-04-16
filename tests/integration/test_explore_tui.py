"""Integration tests for the palace explore TUI command — T_13."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from palace.cli.main import app
from palace.cli.ui.app import PalaceApp
from palace.storage.duckdb_store import DuckDBStore

SAMPLE_PROJECT = Path(__file__).parent.parent / "fixtures" / "sample_project"


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def cli_runner() -> CliRunner:
    """Typer CLI test runner."""
    return CliRunner()


def _make_mock_palace(store: DuckDBStore | None = None) -> Any:
    """Return a minimal palace-like object suitable for TUI tests.

    Why a mock instead of a real Palace: TUI tests must not touch the
    filesystem and must run in-process without a .palace/ directory.
    The DuckDBStore(:memory:) satisfies all store method calls.
    """
    palace = MagicMock()
    if store is None:
        s = DuckDBStore(":memory:")
        s.initialize_schema()
        store = s
    palace.store = store
    palace.vector_store = None
    return palace


# ---------------------------------------------------------------------------
# T_13.1 — App lifecycle
# ---------------------------------------------------------------------------


class TestExploreTUI:
    @pytest.mark.asyncio
    async def test_app_launches_and_exits_cleanly(self) -> None:
        """T_13.1: PalaceApp launches with in-memory store and exits on 'q'."""
        mock_palace = _make_mock_palace()
        app_instance = PalaceApp(mock_palace)
        async with app_instance.run_test() as pilot:
            # App is running — DomainMapView will show empty-state message.
            await pilot.press("q")
        # No exception raised → clean exit.

    @pytest.mark.asyncio
    async def test_empty_state_message_shown(self) -> None:
        """T_13.1: DomainMapView shows 'No domains found' when store is empty."""
        from textual.widgets import ListView

        mock_palace = _make_mock_palace()
        app_instance = PalaceApp(mock_palace)
        async with app_instance.run_test() as pilot:
            domain_map = app_instance.query_one("#main", ListView)
            items = list(domain_map.query("ListItem"))
            # Should have exactly one empty-state item.
            assert len(items) == 1

    @pytest.mark.asyncio
    async def test_search_overlay_opens_on_slash(self) -> None:
        """T_13.1: Pressing '/' pushes SearchOverlay onto the screen stack."""
        from palace.cli.ui.widgets.search_overlay import SearchOverlay

        mock_palace = _make_mock_palace()
        app_instance = PalaceApp(mock_palace)
        async with app_instance.run_test() as pilot:
            await pilot.press("/")
            # Top of stack should now be SearchOverlay.
            assert isinstance(app_instance.screen, SearchOverlay)

    @pytest.mark.asyncio
    async def test_escape_does_not_crash_at_root(self) -> None:
        """T_13.1: Pressing Escape at root (stack depth 1) is a no-op."""
        mock_palace = _make_mock_palace()
        app_instance = PalaceApp(mock_palace)
        async with app_instance.run_test() as pilot:
            # Should not raise even though there is nothing to pop.
            await pilot.press("escape")
            # Still alive — can still quit.
            await pilot.press("q")

    @pytest.mark.asyncio
    async def test_escape_pops_search_overlay(self) -> None:
        """T_13.1: Escape closes SearchOverlay and returns to root."""
        from palace.cli.ui.app import PalaceApp as _App

        mock_palace = _make_mock_palace()
        app_instance = _App(mock_palace)
        async with app_instance.run_test() as pilot:
            await pilot.press("/")
            await pilot.press("escape")
            # Back to root — screen stack depth is 1.
            assert len(app_instance.screen_stack) == 1


# ---------------------------------------------------------------------------
# T_13.1 — CLI integration
# ---------------------------------------------------------------------------


class TestExploreCLI:
    def test_cli_no_palace(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """T_13.1: explore without palace exits 1 with an error message."""
        original_cwd = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            result = cli_runner.invoke(app, ["explore"])
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 1
        assert "No palace found" in result.output or "palace init" in result.output

    def test_cli_help(self, cli_runner: CliRunner) -> None:
        """T_13.1: palace explore --help exits 0 and shows description."""
        result = cli_runner.invoke(app, ["explore", "--help"])
        assert result.exit_code == 0
        assert "TUI" in result.output or "explore" in result.output.lower()
