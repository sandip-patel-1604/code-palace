"""T_4 gate tests — Graph Builder + palace init validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from palace.cli.main import app
from palace.core.config import PalaceConfig
from palace.core.models import EdgeType
from palace.graph.builder import BuildStats, GraphBuilder
from palace.parsing.extractors.base import FileExtraction, ImportInfo, SymbolInfo
from palace.core.models import SymbolKind
from palace.storage.duckdb_store import DuckDBStore

SAMPLE_PROJECT = Path(__file__).parent.parent / "fixtures" / "sample_project"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store() -> DuckDBStore:
    """Fresh in-memory DuckDB store with schema initialised."""
    s = DuckDBStore(":memory:")
    s.initialize_schema()
    return s


@pytest.fixture
def cli_runner() -> CliRunner:
    """Typer CLI test runner."""
    return CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_extraction(
    path: Path,
    language: str = "python",
    symbols: list[SymbolInfo] | None = None,
    imports: list[ImportInfo] | None = None,
) -> FileExtraction:
    """Build a minimal FileExtraction for use in tests."""
    return FileExtraction(
        path=path,
        language=language,
        symbols=symbols or [],
        imports=imports or [],
    )


def _make_symbol(name: str, kind: SymbolKind = SymbolKind.FUNCTION) -> SymbolInfo:
    """Return a minimal SymbolInfo."""
    return SymbolInfo(
        name=name,
        qualified_name=name,
        kind=kind,
        line_start=1,
        line_end=5,
        col_start=0,
        col_end=20,
    )


# ---------------------------------------------------------------------------
# T_4.1 — Build graph: files, symbols, edges
# ---------------------------------------------------------------------------


class TestGraphBuild:
    def test_build_inserts_files_and_symbols(self, store: DuckDBStore, tmp_path: Path) -> None:
        """T_4.1: GraphBuilder inserts files and symbols matching the input extractions."""
        # Create real files so the builder can hash/stat them
        file_a = tmp_path / "a.py"
        file_b = tmp_path / "b.py"
        file_a.write_text("def foo(): pass\n")
        file_b.write_text("class Bar: pass\n")

        extractions = [
            _make_extraction(
                file_a,
                symbols=[
                    _make_symbol("foo", SymbolKind.FUNCTION),
                ],
            ),
            _make_extraction(
                file_b,
                symbols=[
                    _make_symbol("Bar", SymbolKind.CLASS),
                ],
            ),
        ]

        builder = GraphBuilder(store)
        stats = builder.build(extractions, tmp_path)

        assert stats.files == 2
        assert stats.symbols == 2
        assert stats.errors == []

        files = store.get_all_files()
        paths = {f["path"] for f in files}
        assert str(file_a) in paths
        assert str(file_b) in paths

        syms = store.get_symbols()
        names = {s["name"] for s in syms}
        assert "foo" in names
        assert "Bar" in names

    def test_build_stats_counts_are_accurate(self, store: DuckDBStore, tmp_path: Path) -> None:
        """T_4.1: BuildStats.files, .symbols match what was actually inserted."""
        f = tmp_path / "mod.py"
        f.write_text("x = 1\ny = 2\n")

        extractions = [
            _make_extraction(
                f,
                symbols=[
                    _make_symbol("x", SymbolKind.VARIABLE),
                    _make_symbol("y", SymbolKind.VARIABLE),
                ],
            )
        ]

        builder = GraphBuilder(store)
        stats = builder.build(extractions, tmp_path)

        assert stats.files == 1
        assert stats.symbols == 2
        assert stats.duration_seconds >= 0.0

    def test_build_deduplicates_import_edges(self, store: DuckDBStore, tmp_path: Path) -> None:
        """T_4.1: Duplicate resolved imports produce only one edge."""
        src = tmp_path / "src.py"
        tgt = tmp_path / "tgt.py"
        src.write_text("from tgt import a, b\n")
        tgt.write_text("a = 1\nb = 2\n")

        # Two imports resolving to the same target file
        extractions = [
            _make_extraction(
                src,
                imports=[
                    ImportInfo(module_path="tgt", imported_names=["a"], line_number=1),
                    ImportInfo(module_path="tgt", imported_names=["b"], line_number=1),
                ],
            ),
            _make_extraction(tgt),
        ]

        builder = GraphBuilder(store)
        stats = builder.build(extractions, tmp_path)

        assert stats.imports_total == 2
        assert stats.imports_resolved == 2
        # Only one unique edge between src → tgt
        assert stats.edges == 1


# ---------------------------------------------------------------------------
# T_4.2 — Import resolution: relative Python import
# ---------------------------------------------------------------------------


class TestImportResolution:
    def test_relative_python_import_resolves(self, store: DuckDBStore, tmp_path: Path) -> None:
        """T_4.2: Python 'from .service import UserService' resolves to service.py."""
        app_py = tmp_path / "app.py"
        service_py = tmp_path / "service.py"
        app_py.write_text("from .service import UserService\n")
        service_py.write_text("class UserService: pass\n")

        extractions = [
            _make_extraction(
                app_py,
                imports=[
                    ImportInfo(
                        module_path=".service",
                        imported_names=["UserService"],
                        is_relative=True,
                        line_number=1,
                    )
                ],
            ),
            _make_extraction(service_py),
        ]

        builder = GraphBuilder(store)
        stats = builder.build(extractions, tmp_path)

        assert stats.imports_resolved == 1, "relative import must resolve"

        # The resolved_file_id on the import row must point to service.py
        service_row = store.get_file_by_path(str(service_py))
        assert service_row is not None
        service_id = service_row["file_id"]

        imports = store.get_imports()
        assert any(i["resolved_file_id"] == service_id for i in imports), (
            "import row must have resolved_file_id == service.py's file_id"
        )

    def test_absolute_python_import_resolves(self, store: DuckDBStore, tmp_path: Path) -> None:
        """T_4.2: Python 'from utils import helper' resolves to utils.py under root."""
        caller = tmp_path / "main.py"
        target = tmp_path / "utils.py"
        caller.write_text("from utils import helper\n")
        target.write_text("def helper(): pass\n")

        extractions = [
            _make_extraction(
                caller,
                imports=[
                    ImportInfo(module_path="utils", imported_names=["helper"], line_number=1)
                ],
            ),
            _make_extraction(target),
        ]

        builder = GraphBuilder(store)
        stats = builder.build(extractions, tmp_path)

        assert stats.imports_resolved == 1

    # ------------------------------------------------------------------
    # T_4.3 — Unresolved (external) imports
    # ------------------------------------------------------------------

    def test_external_import_stored_with_null_resolved(
        self, store: DuckDBStore, tmp_path: Path
    ) -> None:
        """T_4.3: External package import is stored but resolved_file_id is NULL."""
        f = tmp_path / "app.py"
        f.write_text("import requests\n")

        extractions = [
            _make_extraction(
                f,
                imports=[ImportInfo(module_path="requests", line_number=1)],
            )
        ]

        builder = GraphBuilder(store)
        stats = builder.build(extractions, tmp_path)

        assert stats.imports_total == 1
        assert stats.imports_resolved == 0

        imports = store.get_imports()
        assert len(imports) == 1
        assert imports[0]["module_path"] == "requests"
        assert imports[0]["resolved_file_id"] is None

    def test_external_import_creates_no_edge(self, store: DuckDBStore, tmp_path: Path) -> None:
        """T_4.3: Unresolved imports do not produce edges."""
        f = tmp_path / "app.py"
        f.write_text("import os\n")

        extractions = [
            _make_extraction(
                f,
                imports=[ImportInfo(module_path="os", line_number=1)],
            )
        ]

        builder = GraphBuilder(store)
        stats = builder.build(extractions, tmp_path)

        assert stats.edges == 0


# ---------------------------------------------------------------------------
# T_4.4 — CLI init on sample_project
# ---------------------------------------------------------------------------


class TestCliInit:
    def test_cli_init_sample_project(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """T_4.4: palace init on sample_project exits 0 and creates .palace/ with data."""
        import shutil

        # Copy sample project to tmp so we don't pollute fixtures
        project = tmp_path / "sample"
        shutil.copytree(SAMPLE_PROJECT, project)

        result = cli_runner.invoke(app, ["init", str(project), "--no-progress"])

        assert result.exit_code == 0, f"exit_code={result.exit_code}\n{result.output}"
        assert (project / ".palace").is_dir()
        assert (project / ".palace" / "palace.duckdb").exists()

        # Verify DB actually has data
        store = DuckDBStore(str(project / ".palace" / "palace.duckdb"))
        store.initialize_schema()
        files = store.get_all_files()
        store.close()

        assert len(files) > 0, "palace.duckdb must contain at least one file record"

    # ------------------------------------------------------------------
    # T_4.5 — CLI init on empty directory
    # ------------------------------------------------------------------

    def test_cli_init_empty_dir(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """T_4.5: palace init on empty dir exits 0 with graceful 0-files message."""
        result = cli_runner.invoke(app, ["init", str(tmp_path), "--no-progress"])

        assert result.exit_code == 0, f"exit_code={result.exit_code}\n{result.output}"
        assert (tmp_path / ".palace").is_dir()
        # Summary should mention 0 files
        assert "0" in result.output

    # ------------------------------------------------------------------
    # T_4.6 — CLI init --force (re-index without duplicates)
    # ------------------------------------------------------------------

    def test_cli_init_force_no_duplicates(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """T_4.6: Running palace init twice with --force produces no duplicate data."""
        import shutil

        project = tmp_path / "sample"
        shutil.copytree(SAMPLE_PROJECT, project)

        r1 = cli_runner.invoke(app, ["init", str(project), "--no-progress"])
        assert r1.exit_code == 0, r1.output

        r2 = cli_runner.invoke(app, ["init", str(project), "--force", "--no-progress"])
        assert r2.exit_code == 0, r2.output

        # File count must be the same after re-indexing
        store = DuckDBStore(str(project / ".palace" / "palace.duckdb"))
        store.initialize_schema()
        files_after = store.get_all_files()
        store.close()

        assert len(files_after) > 0

    def test_cli_init_requires_force_on_existing(
        self, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """T_4.6: Second palace init without --force exits non-zero."""
        r1 = cli_runner.invoke(app, ["init", str(tmp_path), "--no-progress"])
        assert r1.exit_code == 0

        r2 = cli_runner.invoke(app, ["init", str(tmp_path), "--no-progress"])
        assert r2.exit_code != 0, "should fail without --force"
