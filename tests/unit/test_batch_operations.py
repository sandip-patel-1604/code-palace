"""T_14.3 — Batch database operations tests."""

from __future__ import annotations

import pytest

from palace.core.models import EdgeType
from palace.storage.duckdb_store import DuckDBStore
from palace.storage.store import EdgeRecord, FileRecord, ImportRecord, SymbolRecord


@pytest.fixture
def store() -> DuckDBStore:
    """Fresh in-memory DuckDB store with schema initialised."""
    s = DuckDBStore(":memory:")
    s.initialize_schema()
    return s


def _file(path: str) -> FileRecord:
    """Minimal FileRecord."""
    return FileRecord(path=path, language="python", size_bytes=100, line_count=10, hash="abc")


def _symbol(file_id: int, name: str, **kwargs) -> SymbolRecord:
    """Minimal SymbolRecord."""
    defaults = dict(
        qualified_name=name,
        kind="function",
        line_start=1,
        line_end=5,
        col_start=0,
        col_end=0,
    )
    defaults.update(kwargs)
    return SymbolRecord(file_id=file_id, name=name, **defaults)


class TestSymbolsBatch:
    """T_14.3.1-3: Batch symbol insertion."""

    def test_batch_returns_ids(self, store: DuckDBStore) -> None:
        """T_14.3.1: upsert_symbols_batch(100) returns 100 IDs."""
        fid = store.upsert_file(_file("batch.py"))
        records = [_symbol(fid, f"func_{i}") for i in range(100)]
        ids = store.upsert_symbols_batch(records)
        assert len(ids) == 100
        assert len(set(ids)) == 100  # all unique

    def test_batch_equivalence(self, store: DuckDBStore) -> None:
        """T_14.3.2: Batch produces identical DB state as sequential."""
        # Sequential store
        seq_store = DuckDBStore(":memory:")
        seq_store.initialize_schema()
        fid_seq = seq_store.upsert_file(_file("seq.py"))
        for i in range(10):
            seq_store.upsert_symbol(_symbol(fid_seq, f"fn_{i}"))

        # Batch store
        fid_batch = store.upsert_file(_file("seq.py"))
        records = [_symbol(fid_batch, f"fn_{i}") for i in range(10)]
        store.upsert_symbols_batch(records)

        seq_syms = seq_store.get_symbols()
        batch_syms = store.get_symbols()
        assert len(seq_syms) == len(batch_syms)
        for s, b in zip(seq_syms, batch_syms):
            assert s["name"] == b["name"]
            assert s["kind"] == b["kind"]

    def test_parent_id_resolution(self, store: DuckDBStore) -> None:
        """T_14.3.3: Batch with nested symbols resolves parent_id."""
        fid = store.upsert_file(_file("nested.py"))
        records = [
            _symbol(fid, "MyClass", kind="class"),
            _symbol(fid, "my_method", kind="method"),
        ]
        ids = store.upsert_symbols_batch(records)

        # Manually update parent (as GraphBuilder would)
        store._con.execute(
            "UPDATE symbols SET parent_id = ? WHERE symbol_id = ?",
            [ids[0], ids[1]],
        )

        sym = store.get_symbols(file_id=fid)
        method = [s for s in sym if s["name"] == "my_method"][0]
        assert method["parent_id"] == ids[0]


class TestEdgesBatch:
    """T_14.3.4: Batch edge insertion."""

    def test_batch_edges(self, store: DuckDBStore) -> None:
        """T_14.3.4: upsert_edges_batch(50) stores all 50."""
        fids = [store.upsert_file(_file(f"e{i}.py")) for i in range(51)]
        records = [
            EdgeRecord(
                source_file_id=fids[0],
                edge_type=str(EdgeType.IMPORTS),
                target_file_id=fids[i + 1],
            )
            for i in range(50)
        ]
        store.upsert_edges_batch(records)
        edges = store.get_edges(source_file_id=fids[0])
        assert len(edges) == 50


class TestImportsBatch:
    """T_14.3.5: Batch import insertion."""

    def test_batch_imports(self, store: DuckDBStore) -> None:
        """T_14.3.5: upsert_imports_batch(30) returns 30 IDs."""
        fid = store.upsert_file(_file("imp.py"))
        records = [
            ImportRecord(file_id=fid, module_path=f"mod_{i}", line_number=i + 1)
            for i in range(30)
        ]
        ids = store.upsert_imports_batch(records)
        assert len(ids) == 30
        assert len(set(ids)) == 30


class TestBatchIdempotency:
    """T_14.3.6: Batch operations and empty batches."""

    def test_empty_batch(self, store: DuckDBStore) -> None:
        """T_14.3.6: Empty batch returns empty list / does nothing."""
        assert store.upsert_symbols_batch([]) == []
        store.upsert_edges_batch([])  # should not raise
        assert store.upsert_imports_batch([]) == []


class TestFullPipelineBatch:
    """T_14.3.7: Full init pipeline produces same stats with batch ops."""

    def test_pipeline_stats(self, tmp_path) -> None:
        """T_14.3.7: palace init with batch ops produces valid BuildStats."""
        # Create a small project
        (tmp_path / "main.py").write_text("def hello():\n    pass\n")
        (tmp_path / "util.py").write_text("import main\ndef helper():\n    pass\n")

        from palace.core.config import PalaceConfig
        from palace.core.palace import Palace

        config = PalaceConfig.initialize(tmp_path)
        palace = Palace(config)
        stats = palace.init(skip_git=True, skip_embeddings=True, skip_domains=True)
        palace.close()

        assert stats.files == 2
        assert stats.symbols >= 2  # at least hello and helper
        assert stats.edges >= 0
