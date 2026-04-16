"""T_5 gate tests — palace symbols command validation."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from palace.cli.main import app

SAMPLE_PROJECT = Path(__file__).parent.parent / "fixtures" / "sample_project"


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def cli_runner() -> CliRunner:
    """Typer CLI test runner."""
    return CliRunner()


@pytest.fixture()
def indexed_project(tmp_path: Path) -> Path:
    """Copy sample_project to tmp, run palace init, return the project root."""
    project = tmp_path / "sample"
    shutil.copytree(SAMPLE_PROJECT, project)
    runner = CliRunner()
    result = runner.invoke(app, ["init", str(project), "--no-progress"])
    assert result.exit_code == 0, f"init failed:\n{result.output}"
    return project


# ---------------------------------------------------------------------------
# T_5.1 — Symbols table: shows expected symbol names
# ---------------------------------------------------------------------------


class TestSymbolsTable:
    def test_symbols_table_shows_known_symbols(
        self, cli_runner: CliRunner, indexed_project: Path
    ) -> None:
        """T_5.1: palace symbols on indexed fixture shows symbols in table format."""
        original_cwd = os.getcwd()
        try:
            os.chdir(str(indexed_project))
            result = cli_runner.invoke(app, ["symbols"], catch_exceptions=False)
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 0, f"exit_code={result.exit_code}\n{result.output}"
        # Known symbols from the fixture project
        assert "Application" in result.output
        assert "UserService" in result.output
        assert "create_app" in result.output

    def test_symbols_header_shows_result_count(
        self, cli_runner: CliRunner, indexed_project: Path
    ) -> None:
        """T_5.1: Symbols output includes a result count header."""
        original_cwd = os.getcwd()
        try:
            os.chdir(str(indexed_project))
            result = cli_runner.invoke(app, ["symbols"], catch_exceptions=False)
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 0, result.output
        # Header line with "Symbols" and "results"
        assert "Symbols" in result.output
        assert "results" in result.output


# ---------------------------------------------------------------------------
# T_5.2 — Symbols filter: --kind class returns only classes
# ---------------------------------------------------------------------------


class TestSymbolsKindFilter:
    def test_kind_class_returns_only_classes(
        self, cli_runner: CliRunner, indexed_project: Path
    ) -> None:
        """T_5.2: --kind class returns only symbols with kind=class."""
        original_cwd = os.getcwd()
        try:
            os.chdir(str(indexed_project))
            result = cli_runner.invoke(
                app, ["symbols", "--kind", "class", "--format", "json"],
                catch_exceptions=False,
            )
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 0, f"exit_code={result.exit_code}\n{result.output}"
        data = json.loads(result.output)
        assert len(data) > 0, "Expected at least one class symbol"
        for sym in data:
            assert sym["kind"] == "class", f"Non-class symbol found: {sym}"

    def test_known_classes_are_present(
        self, cli_runner: CliRunner, indexed_project: Path
    ) -> None:
        """T_5.2: Known classes from fixture project appear in --kind class results."""
        original_cwd = os.getcwd()
        try:
            os.chdir(str(indexed_project))
            result = cli_runner.invoke(
                app, ["symbols", "--kind", "class", "--format", "json"],
                catch_exceptions=False,
            )
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        names = {s["name"] for s in data}
        assert "Application" in names, f"Application not in classes: {names}"
        assert "UserService" in names, f"UserService not in classes: {names}"


# ---------------------------------------------------------------------------
# T_5.3 — Symbols JSON: --format json is valid JSON
# ---------------------------------------------------------------------------


class TestSymbolsJsonFormat:
    def test_json_output_is_valid(
        self, cli_runner: CliRunner, indexed_project: Path
    ) -> None:
        """T_5.3: --format json output is parseable JSON."""
        original_cwd = os.getcwd()
        try:
            os.chdir(str(indexed_project))
            result = cli_runner.invoke(
                app, ["symbols", "--format", "json"],
                catch_exceptions=False,
            )
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 0, f"exit_code={result.exit_code}\n{result.output}"
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_json_output_has_expected_fields(
        self, cli_runner: CliRunner, indexed_project: Path
    ) -> None:
        """T_5.3: JSON symbols have all expected dict keys."""
        original_cwd = os.getcwd()
        try:
            os.chdir(str(indexed_project))
            result = cli_runner.invoke(
                app, ["symbols", "--format", "json", "--limit", "1"],
                catch_exceptions=False,
            )
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert len(data) == 1
        sym = data[0]
        for field in ("symbol_id", "file_id", "name", "kind", "line_start"):
            assert field in sym, f"Missing field: {field}"

    def test_json_limit_respected(
        self, cli_runner: CliRunner, indexed_project: Path
    ) -> None:
        """T_5.3: --limit N returns at most N results in JSON output."""
        original_cwd = os.getcwd()
        try:
            os.chdir(str(indexed_project))
            result = cli_runner.invoke(
                app, ["symbols", "--format", "json", "--limit", "3"],
                catch_exceptions=False,
            )
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert len(data) <= 3


# ---------------------------------------------------------------------------
# T_5.7 — No palace: run symbols without palace init
# ---------------------------------------------------------------------------


class TestSymbolsNoPalace:
    def test_no_palace_exits_with_error(
        self, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """T_5.7: palace symbols without .palace/ gives clear error and exit code 1."""
        original_cwd = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            result = cli_runner.invoke(app, ["symbols"])
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 1
        assert "No palace found" in result.output or "palace init" in result.output

    def test_symbols_tree_format_renders(
        self, cli_runner: CliRunner, indexed_project: Path
    ) -> None:
        """T_5.7: --format tree renders a tree without errors."""
        original_cwd = os.getcwd()
        try:
            os.chdir(str(indexed_project))
            result = cli_runner.invoke(
                app, ["symbols", "--format", "tree"],
                catch_exceptions=False,
            )
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 0, f"exit_code={result.exit_code}\n{result.output}"
        assert "Symbols" in result.output
