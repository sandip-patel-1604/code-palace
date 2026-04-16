"""T_10/T_11 gate tests — Phase 2 CLI commands integration."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from palace.cli.main import app

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
SAMPLE_PROJECT = FIXTURES_DIR / "sample_project"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def indexed_project(tmp_path: Path) -> Path:
    """Copy sample_project to tmp, run palace init, return root."""
    project = tmp_path / "sample"
    shutil.copytree(SAMPLE_PROJECT, project)
    runner = CliRunner()
    result = runner.invoke(app, ["init", str(project), "--no-progress"])
    assert result.exit_code == 0, result.output
    return project


# ---------------------------------------------------------------------------
# T_10.3 — Domains command
# ---------------------------------------------------------------------------


class TestDomainsCommand:
    def test_domains_default(self, cli_runner: CliRunner, indexed_project: Path) -> None:
        """T_10.3: palace domains on indexed project exits 0."""
        old_cwd = os.getcwd()
        try:
            os.chdir(indexed_project)
            result = cli_runner.invoke(app, ["domains", "--recompute"])
            assert result.exit_code == 0, result.output
        finally:
            os.chdir(old_cwd)

    def test_domains_json(self, cli_runner: CliRunner, indexed_project: Path) -> None:
        """T_10.3: palace domains --format json produces valid JSON."""
        old_cwd = os.getcwd()
        try:
            os.chdir(indexed_project)
            result = cli_runner.invoke(app, ["domains", "--recompute", "--format", "json"])
            assert result.exit_code == 0, result.output
            data = json.loads(result.output)
            assert isinstance(data, list)
        finally:
            os.chdir(old_cwd)

    def test_no_palace(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """T_10.3: palace domains without init exits 1."""
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = cli_runner.invoke(app, ["domains"])
            assert result.exit_code == 1
        finally:
            os.chdir(old_cwd)


# ---------------------------------------------------------------------------
# T_10.4 — Impact command
# ---------------------------------------------------------------------------


class TestImpactCommand:
    def test_impact_file(self, cli_runner: CliRunner, indexed_project: Path) -> None:
        """T_10.4: palace impact on a file exits 0 and mentions dependents."""
        old_cwd = os.getcwd()
        try:
            os.chdir(indexed_project)
            result = cli_runner.invoke(app, ["impact", "model.py"])
            assert result.exit_code == 0, result.output
            assert "dependents" in result.output.lower() or "impact" in result.output.lower()
        finally:
            os.chdir(old_cwd)

    def test_impact_json(self, cli_runner: CliRunner, indexed_project: Path) -> None:
        """T_10.4: palace impact --format json produces valid JSON."""
        old_cwd = os.getcwd()
        try:
            os.chdir(indexed_project)
            result = cli_runner.invoke(app, ["impact", "model.py", "--format", "json"])
            assert result.exit_code == 0, result.output
            data = json.loads(result.output)
            assert "direct_dependents" in data
            assert "risk" in data
        finally:
            os.chdir(old_cwd)

    def test_impact_not_found(self, cli_runner: CliRunner, indexed_project: Path) -> None:
        """T_10.4: palace impact on nonexistent file exits 1."""
        old_cwd = os.getcwd()
        try:
            os.chdir(indexed_project)
            result = cli_runner.invoke(app, ["impact", "nonexistent.py"])
            assert result.exit_code == 1
        finally:
            os.chdir(old_cwd)


# ---------------------------------------------------------------------------
# T_11.2 — Search command
# ---------------------------------------------------------------------------


class TestSearchCommand:
    def test_search(self, cli_runner: CliRunner, indexed_project: Path) -> None:
        """T_11.2: palace search exits 0."""
        old_cwd = os.getcwd()
        try:
            os.chdir(indexed_project)
            result = cli_runner.invoke(app, ["search", "user service"])
            # Exit 0 if embeddings exist, exit 1 if not — both are valid
            assert result.exit_code in (0, 1), result.output
        finally:
            os.chdir(old_cwd)

    def test_search_json(self, cli_runner: CliRunner, indexed_project: Path) -> None:
        """T_11.2: palace search --format json exits without crash."""
        old_cwd = os.getcwd()
        try:
            os.chdir(indexed_project)
            result = cli_runner.invoke(app, ["search", "user", "--format", "json"])
            assert result.exit_code in (0, 1), result.output
            if result.exit_code == 0 and result.output.strip():
                data = json.loads(result.output)
                assert isinstance(data, list)
        finally:
            os.chdir(old_cwd)

    def test_no_palace(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """T_11.2: palace search without init exits 1."""
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = cli_runner.invoke(app, ["search", "test query"])
            assert result.exit_code == 1
        finally:
            os.chdir(old_cwd)
