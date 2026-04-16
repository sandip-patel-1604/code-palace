"""LanceDB-backed implementation of the VectorStore protocol."""

from __future__ import annotations

from typing import Any

import lancedb
import pyarrow as pa

# Vector dimensionality used throughout Code Palace embeddings.
# Changing this constant requires re-indexing all stored embeddings.
_VECTOR_DIM = 768

# LanceDB table names — kept as constants so callers can reference them
# without hard-coding strings in multiple places.
_SYMBOL_TABLE = "symbol_embeddings"
_FILE_TABLE = "file_embeddings"

# PyArrow schema for the symbol_embeddings table.
# All metadata columns are stored alongside the fixed-width vector column.
_SYMBOL_SCHEMA = pa.schema(
    [
        pa.field("symbol_id", pa.int64()),
        pa.field("file_id", pa.int64()),
        pa.field("name", pa.string()),
        pa.field("qualified_name", pa.string()),
        pa.field("kind", pa.string()),
        pa.field("file_path", pa.string()),
        pa.field("text", pa.string()),
        pa.field("vector", pa.list_(pa.float32(), _VECTOR_DIM)),
    ]
)

# PyArrow schema for the file_embeddings table.
_FILE_SCHEMA = pa.schema(
    [
        pa.field("file_id", pa.int64()),
        pa.field("path", pa.string()),
        pa.field("language", pa.string()),
        pa.field("text", pa.string()),
        pa.field("vector", pa.list_(pa.float32(), _VECTOR_DIM)),
    ]
)


class LanceDBVectorStore:
    """Persistent vector-embedding storage backed by LanceDB.

    Two tables are maintained:
    - ``symbol_embeddings`` — one row per symbol, keyed by symbol_id.
    - ``file_embeddings``   — one row per file, keyed by file_id.

    Both tables use 768-dimensional float32 vectors.  Upserts are
    implemented via LanceDB's merge-insert (update-or-insert) operation so
    that re-indexing a symbol/file does not accumulate duplicate rows.

    Pass ``db_path="/path/to/dir"`` for a persistent store, or any
    temporary directory (e.g. ``tmp_path`` in tests) for an ephemeral one.
    LanceDB does not support an in-memory URI for local connections, so
    tests must use a real filesystem path.
    """

    def __init__(self, db_path: str) -> None:
        # Opening an existing directory is safe — LanceDB creates it if absent.
        self._db: lancedb.DBConnection = lancedb.connect(db_path)
        self._symbol_tbl: Any = self._open_or_create_table(_SYMBOL_TABLE, _SYMBOL_SCHEMA)
        self._file_tbl: Any = self._open_or_create_table(_FILE_TABLE, _FILE_SCHEMA)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _open_or_create_table(self, name: str, schema: pa.Schema) -> Any:
        """Return an existing LanceDB table or create a new empty one.

        Using ``exist_ok=True`` on ``create_table`` is the idiomatic way to
        open-or-create in LanceDB ≥0.5.  If the table already exists the
        schema argument is ignored and the stored schema is used.
        """
        return self._db.create_table(name, schema=schema, exist_ok=True)

    @staticmethod
    def _to_float32_list(vector: list[float]) -> list[float]:
        """Clamp vector values to float32 precision to avoid schema mismatches.

        LanceDB stores vectors as float32; Python floats are float64.  Passing
        them through this helper avoids silent precision loss warnings.
        """
        return [float(v) for v in vector]

    # ------------------------------------------------------------------
    # VectorStore protocol — symbol embeddings
    # ------------------------------------------------------------------

    def upsert_symbol_embedding(
        self,
        symbol_id: int,
        file_id: int,
        name: str,
        qualified_name: str,
        kind: str,
        file_path: str,
        text: str,
        vector: list[float],
    ) -> None:
        """Store or overwrite the embedding for a symbol.

        Uses merge-insert on ``symbol_id`` so the row count stays at 1
        regardless of how many times the same symbol is re-indexed.
        """
        row = {
            "symbol_id": symbol_id,
            "file_id": file_id,
            "name": name,
            "qualified_name": qualified_name,
            "kind": kind,
            "file_path": file_path,
            "text": text,
            "vector": self._to_float32_list(vector),
        }
        (
            self._symbol_tbl.merge_insert("symbol_id")
            .when_matched_update_all()
            .when_not_matched_insert_all()
            .execute([row])
        )

    def upsert_file_embedding(
        self,
        file_id: int,
        path: str,
        language: str,
        text: str,
        vector: list[float],
    ) -> None:
        """Store or overwrite the embedding for a file.

        Uses merge-insert on ``file_id`` so re-indexing a file produces
        exactly one row, never a duplicate.
        """
        row = {
            "file_id": file_id,
            "path": path,
            "language": language,
            "text": text,
            "vector": self._to_float32_list(vector),
        }
        (
            self._file_tbl.merge_insert("file_id")
            .when_matched_update_all()
            .when_not_matched_insert_all()
            .execute([row])
        )

    # ------------------------------------------------------------------
    # VectorStore protocol — search
    # ------------------------------------------------------------------

    def search_symbols(
        self,
        query_vector: list[float],
        limit: int = 20,
        kind: str | None = None,
    ) -> list[dict]:
        """Vector similarity search over symbol embeddings.

        Returns up to ``limit`` results, optionally filtered by ``kind``.
        Results are ordered most-similar first.  ``score`` is computed as
        ``1 - _distance`` so higher values indicate closer matches.

        Returns an empty list when the table has no rows.
        """
        if self._symbol_tbl.count_rows() == 0:
            return []

        query = (
            self._symbol_tbl.search(self._to_float32_list(query_vector))
            .limit(limit)
        )
        if kind is not None:
            # prefilter=True pushes the filter before the ANN scan for correctness
            # when the table has no vector index (exact scan).
            query = query.where(f"kind = '{kind}'", prefilter=True)

        rows = query.to_list()
        return [
            {
                "symbol_id": r["symbol_id"],
                "file_id": r["file_id"],
                "name": r["name"],
                "qualified_name": r["qualified_name"],
                "kind": r["kind"],
                "file_path": r["file_path"],
                "score": 1.0 - r["_distance"],
            }
            for r in rows
        ]

    def search_files(
        self,
        query_vector: list[float],
        limit: int = 20,
        language: str | None = None,
    ) -> list[dict]:
        """Vector similarity search over file embeddings.

        Returns up to ``limit`` results, optionally filtered by ``language``.
        ``score`` is ``1 - _distance``; higher is more similar.

        Returns an empty list when the table has no rows.
        """
        if self._file_tbl.count_rows() == 0:
            return []

        query = (
            self._file_tbl.search(self._to_float32_list(query_vector))
            .limit(limit)
        )
        if language is not None:
            query = query.where(f"language = '{language}'", prefilter=True)

        rows = query.to_list()
        return [
            {
                "file_id": r["file_id"],
                "path": r["path"],
                "language": r["language"],
                "score": 1.0 - r["_distance"],
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # VectorStore protocol — lifecycle
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Drop both embedding tables, resetting the store to empty.

        Re-creates the tables as empty after dropping so the store is
        immediately usable again without re-instantiation.
        """
        # ignore_missing=True avoids an error if the table was never written.
        for name in (_SYMBOL_TABLE, _FILE_TABLE):
            self._db.drop_table(name, ignore_missing=True)

        # Recreate so the instance remains usable without a new __init__ call.
        self._symbol_tbl = self._open_or_create_table(_SYMBOL_TABLE, _SYMBOL_SCHEMA)
        self._file_tbl = self._open_or_create_table(_FILE_TABLE, _FILE_SCHEMA)

    def close(self) -> None:
        """Close the underlying LanceDB connection.

        LanceDB local connections are lightweight handles; this is a no-op
        at the library level but we honour the protocol contract so callers
        can use context managers or explicit teardown uniformly.
        """
        # lancedb.DBConnection has no explicit close() in the local driver;
        # dropping the reference is sufficient for cleanup.
        del self._db
