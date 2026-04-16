"""Shared test fixtures for Code Palace."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from palace.cli.main import app

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def cli_runner() -> CliRunner:
    """Typer CLI test runner."""
    return CliRunner()


@pytest.fixture
def cli_app():
    """The palace Typer app for testing."""
    return app


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary empty project directory."""
    return tmp_path
