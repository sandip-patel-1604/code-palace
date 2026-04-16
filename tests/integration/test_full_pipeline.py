"""T_6 end-to-end pipeline — init → symbols → deps → plan on the fixture project."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from palace.cli.main import app
from palace.graph.planner import StructuralPlanner
from palace.storage.duckdb_store import DuckDBStore

SAMPLE_PROJECT = Path(__file__).parent.parent / "fixtures" / "sample_project"


class TestFullPipelineEndToEnd:
    def test_init_then_plan_produces_valid_result(
        self, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """T_6.6: Full pipeline init → plan on fixture project succeeds end-to-end."""
        project = tmp_path / "project"
        shutil.copytree(SAMPLE_PROJECT, project)

        # --- Step 1: palace init ---
        r_init = cli_runner.invoke(
            app, ["init", str(project), "--no-progress"], catch_exceptions=False
        )
        assert r_init.exit_code == 0, f"palace init failed:\n{r_init.output}"
        assert (project / ".palace" / "palace.duckdb").exists()

        # --- Step 2: verify the store has files and symbols ---
        store = DuckDBStore(str(project / ".palace" / "palace.duckdb"))
        store.initialize_schema()

        try:
            files = store.get_all_files()
            assert len(files) > 0, "No files indexed after palace init"

            symbols = store.get_symbols()
            assert len(symbols) > 0, "No symbols indexed after palace init"

            # --- Step 3: palace plan via StructuralPlanner ---
            planner = StructuralPlanner(store)
            result = planner.plan("add user service notification")

            assert result.task == "add user service notification"
            assert len(result.keywords) > 0, "Plan produced no keywords"

            # At least service.py and model.py should be relevant
            matched_paths = {mf.path for mf in result.matched_files}
            assert any("service" in p.lower() for p in matched_paths), (
                f"service.py missing from plan. Got: {matched_paths}"
            )

            # All matched files must have a positive score
            for mf in result.matched_files:
                assert mf.relevance_score > 0, f"{mf.path} has zero score"
                assert mf.language in {
                    "python", "typescript", "go", "java", "javascript"
                }, f"Unknown language: {mf.language}"

            # Dependency order: model.py (no deps) should appear before app.py (imports model)
            paths_ordered = [mf.path for mf in result.matched_files]
            model_idx = next(
                (i for i, p in enumerate(paths_ordered) if "model" in p.lower()),
                None,
            )
            app_idx = next(
                (i for i, p in enumerate(paths_ordered) if p.endswith("app.py")),
                None,
            )
            if model_idx is not None and app_idx is not None:
                assert model_idx < app_idx, (
                    "model.py should precede app.py in dependency order"
                )

            # --- Step 4: plan with JSON serialisation round-trip ---
            payload = {
                "task": result.task,
                "keywords": result.keywords,
                "matched_files": [
                    {
                        "file_id": mf.file_id,
                        "path": mf.path,
                        "language": mf.language,
                        "relevance_score": mf.relevance_score,
                    }
                    for mf in result.matched_files
                ],
                "patterns": [p.name for p in result.patterns],
                "suggested_tests": result.suggested_tests,
            }
            serialised = json.dumps(payload)
            parsed = json.loads(serialised)

            assert parsed["task"] == result.task
            assert isinstance(parsed["matched_files"], list)

        finally:
            store.close()

    def test_plan_on_empty_store_is_graceful(
        self, tmp_path: Path
    ) -> None:
        """T_6.6: Planner on an empty (just-initialised) store returns empty result gracefully."""
        store = DuckDBStore(":memory:")
        store.initialize_schema()

        try:
            planner = StructuralPlanner(store)
            result = planner.plan("add webhook handler")

            # Should not raise — just return empty matched_files
            assert isinstance(result.matched_files, list)
            assert isinstance(result.patterns, list)
            assert isinstance(result.suggested_tests, list)
        finally:
            store.close()

    def test_scope_filter_reduces_results(self, tmp_path: Path) -> None:
        """T_6.6: Scope filter glob restricts planner results to matching paths."""
        project = tmp_path / "project"
        shutil.copytree(SAMPLE_PROJECT, project)

        runner = CliRunner()
        r_init = runner.invoke(
            app, ["init", str(project), "--no-progress"], catch_exceptions=False
        )
        assert r_init.exit_code == 0

        store = DuckDBStore(str(project / ".palace" / "palace.duckdb"))
        store.initialize_schema()

        try:
            planner = StructuralPlanner(store)

            result_all = planner.plan("user service")
            result_scoped = planner.plan("user service", scope="*.py")

            # Scoped result must be a subset of unscoped result
            scoped_paths = {mf.path for mf in result_scoped.matched_files}
            for path in scoped_paths:
                assert path.endswith(".py"), f"Non-.py file in scope=*.py result: {path}"

            # Scoped result should have fewer or equal files than unscoped
            assert len(result_scoped.matched_files) <= len(result_all.matched_files)
        finally:
            store.close()
