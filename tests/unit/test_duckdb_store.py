"""T_2 gate tests — DuckDB Storage Layer validation."""

from __future__ import annotations

import pytest

from palace.core.models import EdgeType
from palace.storage.duckdb_store import DuckDBStore
from palace.storage.store import EdgeRecord, FileRecord, ImportRecord, SymbolRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store() -> DuckDBStore:
    """Fresh in-memory DuckDB store with schema initialised."""
    s = DuckDBStore(":memory:")
    s.initialize_schema()
    return s


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _file(path: str, **kwargs) -> FileRecord:
    """Minimal FileRecord with sensible defaults for test use."""
    defaults = dict(language="python", size_bytes=100, line_count=10, hash="abc123")
    defaults.update(kwargs)
    return FileRecord(path=path, **defaults)


def _symbol(file_id: int, name: str, **kwargs) -> SymbolRecord:
    """Minimal SymbolRecord with sensible defaults for test use."""
    defaults = dict(
        qualified_name=name,
        kind="function",
        line_start=1,
        line_end=5,
        col_start=0,
        col_end=20,
    )
    defaults.update(kwargs)
    return SymbolRecord(file_id=file_id, name=name, **defaults)


def _import_edge(source_id: int, target_id: int) -> EdgeRecord:
    """EdgeRecord representing a file-level import relationship."""
    return EdgeRecord(
        source_file_id=source_id,
        target_file_id=target_id,
        edge_type=EdgeType.IMPORTS,
    )


# ---------------------------------------------------------------------------
# T_2.1 — Schema idempotency
# ---------------------------------------------------------------------------


class TestSchemaIdempotency:
    def test_double_initialize_no_error(self, store: DuckDBStore) -> None:
        """T_2.1: Calling initialize_schema() twice must not raise."""
        # First call already happened in the fixture; call again
        store.initialize_schema()  # must be a no-op


# ---------------------------------------------------------------------------
# T_2.2 — File CRUD
# ---------------------------------------------------------------------------


class TestFileCRUD:
    def test_insert_and_retrieve_by_path(self, store: DuckDBStore) -> None:
        """T_2.2: Inserted file is retrievable by path with all fields intact."""
        rec = _file("src/main.py", language="python", size_bytes=512, line_count=42, hash="deadbeef")
        fid = store.upsert_file(rec)

        result = store.get_file_by_path("src/main.py")

        assert result is not None
        assert result["file_id"] == fid
        assert result["path"] == "src/main.py"
        assert result["language"] == "python"
        assert result["size_bytes"] == 512
        assert result["line_count"] == 42
        assert result["hash"] == "deadbeef"

    def test_get_file_by_path_missing_returns_none(self, store: DuckDBStore) -> None:
        """T_2.2: get_file_by_path on an absent path returns None."""
        assert store.get_file_by_path("nonexistent.py") is None

    def test_get_all_files(self, store: DuckDBStore) -> None:
        """T_2.2: get_all_files returns every inserted file."""
        store.upsert_file(_file("a.py"))
        store.upsert_file(_file("b.py"))
        files = store.get_all_files()
        paths = {f["path"] for f in files}
        assert paths == {"a.py", "b.py"}


# ---------------------------------------------------------------------------
# T_2.3 — Symbol CRUD
# ---------------------------------------------------------------------------


class TestSymbolCRUD:
    def test_insert_symbol_with_parent_nesting(self, store: DuckDBStore) -> None:
        """T_2.3: Parent symbol and nested child are stored with correct parent_id."""
        fid = store.upsert_file(_file("module.py"))

        parent_id = store.upsert_symbol(_symbol(fid, "MyClass", kind="class"))
        child_id = store.upsert_symbol(
            _symbol(fid, "my_method", kind="method", parent_id=parent_id)
        )

        symbols = store.get_symbols(file_id=fid)
        by_id = {s["symbol_id"]: s for s in symbols}

        assert by_id[parent_id]["parent_id"] is None
        assert by_id[child_id]["parent_id"] == parent_id

    def test_filter_symbols_by_kind(self, store: DuckDBStore) -> None:
        """T_2.3: get_symbols(kind=...) filters correctly."""
        fid = store.upsert_file(_file("mod.py"))
        store.upsert_symbol(_symbol(fid, "Foo", kind="class"))
        store.upsert_symbol(_symbol(fid, "bar", kind="function"))

        classes = store.get_symbols(kind="class")
        assert len(classes) == 1
        assert classes[0]["name"] == "Foo"


# ---------------------------------------------------------------------------
# T_2.4 — Edge CRUD with NULL optional FKs
# ---------------------------------------------------------------------------


class TestEdgeCRUD:
    def test_edge_with_null_optional_fks(self, store: DuckDBStore) -> None:
        """T_2.4: Edge with NULL target_file_id, source/target symbol IDs inserts cleanly."""
        fid = store.upsert_file(_file("a.py"))

        store.upsert_edge(
            EdgeRecord(
                source_file_id=fid,
                target_file_id=None,
                source_symbol_id=None,
                target_symbol_id=None,
                edge_type=EdgeType.REFERENCES,
            )
        )

        edges = store.get_edges(source_file_id=fid)
        assert len(edges) == 1
        assert edges[0]["target_file_id"] is None
        assert edges[0]["source_symbol_id"] is None
        assert edges[0]["target_symbol_id"] is None

    def test_filter_edges_by_type(self, store: DuckDBStore) -> None:
        """T_2.4: get_edges(edge_type=...) filters by type."""
        fid_a = store.upsert_file(_file("a.py"))
        fid_b = store.upsert_file(_file("b.py"))

        store.upsert_edge(_import_edge(fid_a, fid_b))
        store.upsert_edge(
            EdgeRecord(source_file_id=fid_a, target_file_id=fid_b, edge_type=EdgeType.CALLS)
        )

        imports = store.get_edges(edge_type=EdgeType.IMPORTS)
        assert len(imports) == 1
        assert imports[0]["edge_type"] == EdgeType.IMPORTS


# ---------------------------------------------------------------------------
# T_2.5 — Upsert idempotency
# ---------------------------------------------------------------------------


class TestUpsertIdempotency:
    def test_upsert_file_twice_produces_one_row(self, store: DuckDBStore) -> None:
        """T_2.5: Upserting same path twice yields exactly 1 row with latest values."""
        fid1 = store.upsert_file(_file("src/app.py", hash="hash_v1", size_bytes=100))
        fid2 = store.upsert_file(_file("src/app.py", hash="hash_v2", size_bytes=200))

        # The FK identity must be stable across upserts
        assert fid1 == fid2

        all_files = store.get_all_files()
        assert len(all_files) == 1
        assert all_files[0]["hash"] == "hash_v2"
        assert all_files[0]["size_bytes"] == 200


# ---------------------------------------------------------------------------
# T_2.6 — Transitive dependencies (A→B→C→D)
# ---------------------------------------------------------------------------


class TestTransitiveDependencies:
    def _build_chain(self, store: DuckDBStore) -> tuple[int, int, int, int]:
        """Insert files A, B, C, D and A→B, B→C, C→D import edges."""
        fid_a = store.upsert_file(_file("a.py"))
        fid_b = store.upsert_file(_file("b.py"))
        fid_c = store.upsert_file(_file("c.py"))
        fid_d = store.upsert_file(_file("d.py"))
        store.upsert_edge(_import_edge(fid_a, fid_b))
        store.upsert_edge(_import_edge(fid_b, fid_c))
        store.upsert_edge(_import_edge(fid_c, fid_d))
        return fid_a, fid_b, fid_c, fid_d

    def test_transitive_deps_returns_b_c_d_with_depths(self, store: DuckDBStore) -> None:
        """T_2.6: get_dependencies(A, transitive=True) returns B@1, C@2, D@3."""
        fid_a, fid_b, fid_c, fid_d = self._build_chain(store)

        deps = store.get_dependencies(fid_a, transitive=True)
        depth_by_path = {d["path"]: d["depth"] for d in deps}

        assert set(depth_by_path.keys()) == {"b.py", "c.py", "d.py"}
        assert depth_by_path["b.py"] == 1
        assert depth_by_path["c.py"] == 2
        assert depth_by_path["d.py"] == 3

    def test_direct_deps_only_returns_b(self, store: DuckDBStore) -> None:
        """T_2.6 (non-transitive): get_dependencies(A) returns only B."""
        fid_a, fid_b, fid_c, fid_d = self._build_chain(store)

        deps = store.get_dependencies(fid_a, transitive=False)
        assert len(deps) == 1
        assert deps[0]["path"] == "b.py"


# ---------------------------------------------------------------------------
# T_2.7 — Reverse (transitive) dependents
# ---------------------------------------------------------------------------


class TestTransitiveDependents:
    def test_dependents_of_d_returns_c_b_a(self, store: DuckDBStore) -> None:
        """T_2.7: get_dependents(D, transitive=True) returns C@1, B@2, A@3."""
        fid_a = store.upsert_file(_file("a.py"))
        fid_b = store.upsert_file(_file("b.py"))
        fid_c = store.upsert_file(_file("c.py"))
        fid_d = store.upsert_file(_file("d.py"))
        store.upsert_edge(_import_edge(fid_a, fid_b))
        store.upsert_edge(_import_edge(fid_b, fid_c))
        store.upsert_edge(_import_edge(fid_c, fid_d))

        dependents = store.get_dependents(fid_d, transitive=True)
        depth_by_path = {d["path"]: d["depth"] for d in dependents}

        assert set(depth_by_path.keys()) == {"a.py", "b.py", "c.py"}
        assert depth_by_path["c.py"] == 1
        assert depth_by_path["b.py"] == 2
        assert depth_by_path["a.py"] == 3


# ---------------------------------------------------------------------------
# T_2.8 — Circular import safety
# ---------------------------------------------------------------------------


class TestCircularSafety:
    def test_cycle_terminates_and_returns_b(self, store: DuckDBStore) -> None:
        """T_2.8: A→B→A cycle: get_dependencies(A) terminates and returns B."""
        fid_a = store.upsert_file(_file("a.py"))
        fid_b = store.upsert_file(_file("b.py"))
        store.upsert_edge(_import_edge(fid_a, fid_b))
        store.upsert_edge(_import_edge(fid_b, fid_a))  # cycle

        # Must not hang or raise
        deps = store.get_dependencies(fid_a, transitive=True)
        paths = {d["path"] for d in deps}

        assert "b.py" in paths


# ---------------------------------------------------------------------------
# T_2.9 — Import storage and resolution
# ---------------------------------------------------------------------------


class TestImportStorage:
    def test_insert_unresolved_then_resolve(self, store: DuckDBStore) -> None:
        """T_2.9: Insert import with NULL resolved_file_id, resolve it, verify."""
        fid_a = store.upsert_file(_file("a.py"))
        fid_b = store.upsert_file(_file("b.py"))

        imp_id = store.upsert_import(
            ImportRecord(
                file_id=fid_a,
                module_path="b",
                line_number=1,
                resolved_file_id=None,
            )
        )

        # Before resolution
        imports = store.get_imports(file_id=fid_a)
        assert len(imports) == 1
        assert imports[0]["resolved_file_id"] is None

        # Resolve
        store.resolve_import(imp_id, fid_b)

        imports = store.get_imports(file_id=fid_a)
        assert imports[0]["resolved_file_id"] == fid_b

    def test_get_imports_unfiltered(self, store: DuckDBStore) -> None:
        """T_2.9: get_imports() without filter returns all import rows."""
        fid_a = store.upsert_file(_file("a.py"))
        fid_b = store.upsert_file(_file("b.py"))
        store.upsert_import(ImportRecord(file_id=fid_a, module_path="x", line_number=1))
        store.upsert_import(ImportRecord(file_id=fid_b, module_path="y", line_number=2))

        all_imports = store.get_imports()
        assert len(all_imports) == 2


# ---------------------------------------------------------------------------
# T_2.10 — clear() correctness with self-referential parent_id FK
# ---------------------------------------------------------------------------


class TestClearAndReuse:
    """T_2.10: clear() must delete all rows without dropping tables.

    DuckDB evaluates FK constraints per-row against the original table snapshot,
    so naive DELETE or UPDATE+DELETE approaches fail on multi-level parent_id
    chains.  The leaf-first loop is the correct fix.
    """

    def _populate(self, store: DuckDBStore) -> None:
        """Insert a 3-level symbol hierarchy plus edges, imports, and meta."""
        fid_a = store.upsert_file(_file("a.py"))
        fid_b = store.upsert_file(_file("b.py"))

        # 3-level chain: module → class → method
        mod_id = store.upsert_symbol(_symbol(fid_a, "Module", kind="module"))
        cls_id = store.upsert_symbol(
            _symbol(fid_a, "MyClass", kind="class", parent_id=mod_id)
        )
        store.upsert_symbol(
            _symbol(fid_a, "my_method", kind="method", parent_id=cls_id)
        )

        store.upsert_edge(EdgeRecord(source_file_id=fid_a, target_file_id=fid_b, edge_type=EdgeType.IMPORTS))
        store.upsert_import(ImportRecord(file_id=fid_a, module_path="b", line_number=1))
        store.set_meta("root", "/tmp/project")

    def test_clear_empties_all_tables(self, store: DuckDBStore) -> None:
        """T_2.10: After clear(), every table must have zero rows."""
        self._populate(store)

        store.clear()

        assert store.get_all_files() == []
        assert store.get_symbols() == []
        assert store.get_edges() == []
        assert store.get_imports() == []
        assert store.get_meta("root") is None

    def test_clear_then_reinsert_succeeds(self, store: DuckDBStore) -> None:
        """T_2.10: Tables are reusable after clear() — new rows insert without error."""
        self._populate(store)
        store.clear()

        # Re-insert must not raise
        fid = store.upsert_file(_file("new.py"))
        sid = store.upsert_symbol(_symbol(fid, "NewClass", kind="class"))

        files = store.get_all_files()
        syms = store.get_symbols()
        assert len(files) == 1
        assert files[0]["path"] == "new.py"
        assert len(syms) == 1
        assert syms[0]["symbol_id"] == sid

    def test_clear_self_referential_three_levels(self, store: DuckDBStore) -> None:
        """T_2.10: clear() handles 3-level parent_id chains (the originally failing case).

        DuckDB's per-row FK snapshot evaluation causes UPDATE+DELETE and single-pass
        DELETE approaches to raise ConstraintError on multi-level chains.  The
        leaf-first loop must drain the table correctly.
        """
        fid = store.upsert_file(_file("deep.py"))
        # level-1 root
        root_id = store.upsert_symbol(_symbol(fid, "Root", kind="module"))
        # level-2 parent (parent_id → root)
        mid_id = store.upsert_symbol(_symbol(fid, "Mid", kind="class", parent_id=root_id))
        # level-3 leaf (parent_id → mid)
        store.upsert_symbol(_symbol(fid, "Leaf", kind="method", parent_id=mid_id))

        # Must not raise ConstraintException
        store.clear()

        assert store.get_symbols() == []
        assert store.get_all_files() == []

    def test_clear_is_idempotent(self, store: DuckDBStore) -> None:
        """T_2.10: Calling clear() on an already-empty store must not raise."""
        store.clear()  # No data — all DELETE / loop body should be no-ops
        store.clear()  # Second call on empty store must also be harmless


# ---------------------------------------------------------------------------
# T_14.4 — File Lookup by ID
# ---------------------------------------------------------------------------


class TestFileByIdLookup:
    """T_14.4: O(1) file lookup by primary key."""

    def test_found(self, store: DuckDBStore) -> None:
        """T_14.4.1: get_file_by_id returns correct dict for a valid file_id."""
        fid = store.upsert_file(_file("lookup.py"))
        row = store.get_file_by_id(fid)
        assert row is not None
        assert row["file_id"] == fid
        assert row["path"] == "lookup.py"

    def test_not_found(self, store: DuckDBStore) -> None:
        """T_14.4.2: get_file_by_id returns None for nonexistent ID."""
        result = store.get_file_by_id(99999)
        assert result is None

    def test_same_shape_as_get_all_files(self, store: DuckDBStore) -> None:
        """T_14.4.3: returned dict has same keys as get_all_files() dicts."""
        fid = store.upsert_file(_file("shape.py"))
        by_id = store.get_file_by_id(fid)
        all_files = store.get_all_files()
        assert by_id is not None
        assert len(all_files) == 1
        assert set(by_id.keys()) == set(all_files[0].keys())
