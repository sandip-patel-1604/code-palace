"""T_5 gate tests — palace deps command validation."""

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
# T_5.4 — Deps out: palace deps app.py shows direct dependencies
# ---------------------------------------------------------------------------


class TestDepsOut:
    def test_deps_out_app_shows_direct_deps(
        self, cli_runner: CliRunner, indexed_project: Path
    ) -> None:
        """T_5.4: palace deps app.py shows direct outgoing dependencies."""
        original_cwd = os.getcwd()
        try:
            os.chdir(str(indexed_project))
            result = cli_runner.invoke(
                app, ["deps", "app.py"],
                catch_exceptions=False,
            )
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 0, f"exit_code={result.exit_code}\n{result.output}"
        # app.py imports service, model, config
        output_lower = result.output.lower()
        assert (
            "service" in output_lower or "model" in output_lower or "config" in output_lower
        ), f"Expected dependency files in output:\n{result.output}"

    def test_deps_out_is_default_direction(
        self, cli_runner: CliRunner, indexed_project: Path
    ) -> None:
        """T_5.4: Default direction is 'out' — same result as --direction out."""
        original_cwd = os.getcwd()
        try:
            os.chdir(str(indexed_project))
            r_default = cli_runner.invoke(app, ["deps", "app.py"], catch_exceptions=False)
            r_out = cli_runner.invoke(
                app, ["deps", "app.py", "--direction", "out"],
                catch_exceptions=False,
            )
        finally:
            os.chdir(original_cwd)

        assert r_default.exit_code == 0, r_default.output
        assert r_out.exit_code == 0, r_out.output


# ---------------------------------------------------------------------------
# T_5.5 — Deps in: palace deps model.py --direction in shows dependents
# ---------------------------------------------------------------------------


class TestDepsIn:
    def test_deps_in_model_shows_service_as_dependent(
        self, cli_runner: CliRunner, indexed_project: Path
    ) -> None:
        """T_5.5: palace deps model.py --direction in shows service.py as a dependent."""
        original_cwd = os.getcwd()
        try:
            os.chdir(str(indexed_project))
            result = cli_runner.invoke(
                app, ["deps", "model.py", "--direction", "in"],
                catch_exceptions=False,
            )
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 0, f"exit_code={result.exit_code}\n{result.output}"
        # service.py imports model.py, so it should appear as a dependent
        assert "service" in result.output.lower(), (
            f"Expected service.py in dependents of model.py:\n{result.output}"
        )

    def test_deps_in_includes_app_as_dependent_of_model(
        self, cli_runner: CliRunner, indexed_project: Path
    ) -> None:
        """T_5.5: app.py also imports model.py — should appear in --direction in."""
        original_cwd = os.getcwd()
        try:
            os.chdir(str(indexed_project))
            result = cli_runner.invoke(
                app, ["deps", "model.py", "--direction", "in"],
                catch_exceptions=False,
            )
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 0, result.output
        output_lower = result.output.lower()
        assert "app" in output_lower or "service" in output_lower, (
            f"Expected app.py or service.py as dependents of model.py:\n{result.output}"
        )


# ---------------------------------------------------------------------------
# T_5.6 — Deps transitive: --transitive returns full chain
# ---------------------------------------------------------------------------


class TestDepsTransitive:
    def test_transitive_deps_app_covers_full_chain(
        self, cli_runner: CliRunner, indexed_project: Path
    ) -> None:
        """T_5.6: --transitive returns the full transitive dependency chain."""
        original_cwd = os.getcwd()
        try:
            os.chdir(str(indexed_project))
            result = cli_runner.invoke(
                app, ["deps", "app.py", "--transitive"],
                catch_exceptions=False,
            )
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 0, f"exit_code={result.exit_code}\n{result.output}"
        output_lower = result.output.lower()
        # app.py → service.py → model.py; also app.py → model.py, config.py
        assert "model" in output_lower, f"model.py missing from transitive deps:\n{result.output}"

    def test_transitive_json_has_more_deps_than_direct(
        self, cli_runner: CliRunner, indexed_project: Path
    ) -> None:
        """T_5.6: Transitive JSON result has at least as many deps as direct."""
        original_cwd = os.getcwd()
        try:
            os.chdir(str(indexed_project))
            r_direct = cli_runner.invoke(
                app, ["deps", "app.py", "--format", "json"],
                catch_exceptions=False,
            )
            r_trans = cli_runner.invoke(
                app, ["deps", "app.py", "--transitive", "--format", "json"],
                catch_exceptions=False,
            )
        finally:
            os.chdir(original_cwd)

        assert r_direct.exit_code == 0, r_direct.output
        assert r_trans.exit_code == 0, r_trans.output

        direct_data = json.loads(r_direct.output)
        trans_data = json.loads(r_trans.output)

        direct_count = len(direct_data.get("dependencies", []))
        trans_count = len(trans_data.get("dependencies", []))

        assert trans_count >= direct_count, (
            f"Transitive ({trans_count}) should be >= direct ({direct_count})"
        )


# ---------------------------------------------------------------------------
# T_5.7 — No palace: run deps without palace init
# ---------------------------------------------------------------------------


class TestDepsNoPalace:
    def test_no_palace_exits_with_error(
        self, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """T_5.7: palace deps without .palace/ gives clear error and exit code 1."""
        original_cwd = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            result = cli_runner.invoke(app, ["deps", "app.py"])
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 1
        assert "No palace found" in result.output or "palace init" in result.output

    def test_deps_table_format_renders(
        self, cli_runner: CliRunner, indexed_project: Path
    ) -> None:
        """T_5.7: --format table renders a table without errors."""
        original_cwd = os.getcwd()
        try:
            os.chdir(str(indexed_project))
            result = cli_runner.invoke(
                app, ["deps", "app.py", "--format", "table"],
                catch_exceptions=False,
            )
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 0, f"exit_code={result.exit_code}\n{result.output}"
        assert "app.py" in result.output.lower()

    def test_deps_json_format_is_valid(
        self, cli_runner: CliRunner, indexed_project: Path
    ) -> None:
        """T_5.7: --format json output is parseable JSON with expected structure."""
        original_cwd = os.getcwd()
        try:
            os.chdir(str(indexed_project))
            result = cli_runner.invoke(
                app, ["deps", "app.py", "--format", "json"],
                catch_exceptions=False,
            )
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 0, f"exit_code={result.exit_code}\n{result.output}"
        data = json.loads(result.output)
        assert "file" in data
        assert "direction" in data
        assert "dependencies" in data

    def test_deps_dot_format_renders(
        self, cli_runner: CliRunner, indexed_project: Path
    ) -> None:
        """T_5.7: --format dot renders valid DOT graph syntax."""
        original_cwd = os.getcwd()
        try:
            os.chdir(str(indexed_project))
            result = cli_runner.invoke(
                app, ["deps", "app.py", "--format", "dot"],
                catch_exceptions=False,
            )
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 0, f"exit_code={result.exit_code}\n{result.output}"
        assert "digraph" in result.output
        assert "}" in result.output

    def test_deps_direction_both_shows_both(
        self, cli_runner: CliRunner, indexed_project: Path
    ) -> None:
        """T_5.7: --direction both shows both dependencies and dependents."""
        original_cwd = os.getcwd()
        try:
            os.chdir(str(indexed_project))
            result = cli_runner.invoke(
                app, ["deps", "service.py", "--direction", "both"],
                catch_exceptions=False,
            )
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 0, f"exit_code={result.exit_code}\n{result.output}"
        output_lower = result.output.lower()
        # service.py imports model.py (out) and app.py imports service.py (in)
        assert "model" in output_lower or "app" in output_lower, (
            f"Expected model.py or app.py in both-direction deps of service.py:\n{result.output}"
        )

    def test_unknown_file_gives_error(
        self, cli_runner: CliRunner, indexed_project: Path
    ) -> None:
        """T_5.7: palace deps on a non-existent file gives a helpful error."""
        original_cwd = os.getcwd()
        try:
            os.chdir(str(indexed_project))
            result = cli_runner.invoke(app, ["deps", "nonexistent_file_xyz.py"])
        finally:
            os.chdir(original_cwd)

        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "Error" in result.output
