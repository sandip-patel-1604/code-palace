"""DuckDB-backed implementation of the Store protocol."""

from __future__ import annotations

import json
from typing import Any

import duckdb

from palace.storage.store import EdgeRecord, FileRecord, ImportRecord, SymbolRecord

# Maximum recursion depth for transitive dependency queries.
# Prevents infinite loops when cycles exist in the import graph.
_MAX_DEPTH = 50


class DuckDBStore:
    """Persistent symbol-graph storage backed by DuckDB.

    Uses sequences for auto-increment IDs and recursive CTEs for transitive
    dependency traversal.  Pass db_path=':memory:' for ephemeral test instances.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        # read_only=False is the default; explicit for clarity
        self._con: duckdb.DuckDBPyConnection = duckdb.connect(db_path)

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    def initialize_schema(self) -> None:
        """Create sequences, tables, and indexes.  Safe to call multiple times."""
        stmts = [
            # Sequences — one per table that needs auto-increment IDs
            "CREATE SEQUENCE IF NOT EXISTS file_id_seq START 1",
            "CREATE SEQUENCE IF NOT EXISTS symbol_id_seq START 1",
            "CREATE SEQUENCE IF NOT EXISTS edge_id_seq START 1",
            "CREATE SEQUENCE IF NOT EXISTS import_id_seq START 1",
            # files -------------------------------------------------------
            """
            CREATE TABLE IF NOT EXISTS files (
                file_id      INTEGER PRIMARY KEY DEFAULT nextval('file_id_seq'),
                path         TEXT    NOT NULL UNIQUE,
                language     TEXT    NOT NULL,
                size_bytes   INTEGER NOT NULL,
                line_count   INTEGER NOT NULL,
                hash         TEXT    NOT NULL,
                indexed_at   TIMESTAMP DEFAULT current_timestamp
            )
            """,
            # symbols -----------------------------------------------------
            """
            CREATE TABLE IF NOT EXISTS symbols (
                symbol_id      INTEGER PRIMARY KEY DEFAULT nextval('symbol_id_seq'),
                file_id        INTEGER NOT NULL REFERENCES files(file_id),
                name           TEXT    NOT NULL,
                qualified_name TEXT    NOT NULL,
                kind           TEXT    NOT NULL,
                line_start     INTEGER NOT NULL,
                line_end       INTEGER NOT NULL,
                col_start      INTEGER NOT NULL,
                col_end        INTEGER NOT NULL,
                parent_id      INTEGER REFERENCES symbols(symbol_id),
                signature      TEXT,
                docstring      TEXT,
                is_exported    BOOLEAN DEFAULT true,
                metadata       JSON
            )
            """,
            # edges -------------------------------------------------------
            """
            CREATE TABLE IF NOT EXISTS edges (
                edge_id          INTEGER PRIMARY KEY DEFAULT nextval('edge_id_seq'),
                source_file_id   INTEGER NOT NULL REFERENCES files(file_id),
                target_file_id   INTEGER REFERENCES files(file_id),
                source_symbol_id INTEGER REFERENCES symbols(symbol_id),
                target_symbol_id INTEGER REFERENCES symbols(symbol_id),
                edge_type        TEXT    NOT NULL,
                weight           FLOAT   DEFAULT 1.0,
                metadata         JSON
            )
            """,
            # imports -----------------------------------------------------
            """
            CREATE TABLE IF NOT EXISTS imports (
                import_id        INTEGER PRIMARY KEY DEFAULT nextval('import_id_seq'),
                file_id          INTEGER NOT NULL REFERENCES files(file_id),
                module_path      TEXT    NOT NULL,
                imported_names   TEXT,
                alias            TEXT,
                is_relative      BOOLEAN DEFAULT false,
                line_number      INTEGER NOT NULL,
                resolved_file_id INTEGER REFERENCES files(file_id)
            )
            """,
            # palace_meta -------------------------------------------------
            """
            CREATE TABLE IF NOT EXISTS palace_meta (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT current_timestamp
            )
            """,
            # Indexes on frequently queried columns
            "CREATE INDEX IF NOT EXISTS idx_symbols_file_id  ON symbols(file_id)",
            "CREATE INDEX IF NOT EXISTS idx_symbols_name      ON symbols(name)",
            "CREATE INDEX IF NOT EXISTS idx_symbols_kind      ON symbols(kind)",
            "CREATE INDEX IF NOT EXISTS idx_edges_source      ON edges(source_file_id)",
            "CREATE INDEX IF NOT EXISTS idx_edges_target      ON edges(target_file_id)",
            "CREATE INDEX IF NOT EXISTS idx_edges_type        ON edges(edge_type)",
            "CREATE INDEX IF NOT EXISTS idx_imports_file_id   ON imports(file_id)",
        ]
        for stmt in stmts:
            self._con.execute(stmt)

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def upsert_file(self, record: FileRecord) -> int:
        """Insert or update a file row.  Returns the file_id."""
        row = self._con.execute(
            """
            INSERT INTO files(path, language, size_bytes, line_count, hash)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                language   = excluded.language,
                size_bytes = excluded.size_bytes,
                line_count = excluded.line_count,
                hash       = excluded.hash,
                indexed_at = NOW()
            RETURNING file_id
            """,
            [record.path, record.language, record.size_bytes, record.line_count, record.hash],
        ).fetchone()
        assert row is not None
        return int(row[0])

    def get_file_by_path(self, path: str) -> dict | None:
        """Return the file row for path, or None if not found."""
        row = self._con.execute(
            "SELECT * FROM files WHERE path = ?",
            [path],
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row, self._file_columns())

    def get_all_files(self) -> list[dict]:
        """Return all file rows."""
        rows = self._con.execute("SELECT * FROM files ORDER BY file_id").fetchall()
        cols = self._file_columns()
        return [self._row_to_dict(r, cols) for r in rows]

    # ------------------------------------------------------------------
    # Symbol operations
    # ------------------------------------------------------------------

    def upsert_symbol(self, record: SymbolRecord) -> int:
        """Insert a symbol row.  Returns the symbol_id.

        Symbols are cleared and re-inserted on re-index so no upsert logic is
        needed — this is a plain INSERT that returns the generated ID.
        """
        metadata_json = json.dumps(record.metadata) if record.metadata is not None else None
        row = self._con.execute(
            """
            INSERT INTO symbols(
                file_id, name, qualified_name, kind,
                line_start, line_end, col_start, col_end,
                parent_id, signature, docstring, is_exported, metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING symbol_id
            """,
            [
                record.file_id,
                record.name,
                record.qualified_name,
                record.kind,
                record.line_start,
                record.line_end,
                record.col_start,
                record.col_end,
                record.parent_id,
                record.signature,
                record.docstring,
                record.is_exported,
                metadata_json,
            ],
        ).fetchone()
        assert row is not None
        return int(row[0])

    def get_symbols(
        self,
        file_id: int | None = None,
        kind: str | None = None,
        name_pattern: str | None = None,
    ) -> list[dict]:
        """Return symbols filtered by optional file, kind, or name glob.

        name_pattern uses SQL LIKE syntax (% and _ wildcards).
        """
        conditions: list[str] = []
        params: list[Any] = []

        if file_id is not None:
            conditions.append("file_id = ?")
            params.append(file_id)
        if kind is not None:
            conditions.append("kind = ?")
            params.append(kind)
        if name_pattern is not None:
            conditions.append("name LIKE ?")
            params.append(name_pattern)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self._con.execute(
            f"SELECT * FROM symbols {where} ORDER BY symbol_id",  # noqa: S608
            params,
        ).fetchall()
        cols = self._symbol_columns()
        return [self._row_to_dict(r, cols) for r in rows]

    # ------------------------------------------------------------------
    # Edge operations
    # ------------------------------------------------------------------

    def upsert_edge(self, record: EdgeRecord) -> None:
        """Insert an edge row.  Edges are recreated on re-index, no upsert needed."""
        metadata_json = json.dumps(record.metadata) if record.metadata is not None else None
        self._con.execute(
            """
            INSERT INTO edges(
                source_file_id, target_file_id,
                source_symbol_id, target_symbol_id,
                edge_type, weight, metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                record.source_file_id,
                record.target_file_id,
                record.source_symbol_id,
                record.target_symbol_id,
                record.edge_type,
                record.weight,
                metadata_json,
            ],
        )

    def get_edges(
        self,
        source_file_id: int | None = None,
        target_file_id: int | None = None,
        edge_type: str | None = None,
    ) -> list[dict]:
        """Return edges filtered by optional source, target, or type."""
        conditions: list[str] = []
        params: list[Any] = []

        if source_file_id is not None:
            conditions.append("source_file_id = ?")
            params.append(source_file_id)
        if target_file_id is not None:
            conditions.append("target_file_id = ?")
            params.append(target_file_id)
        if edge_type is not None:
            conditions.append("edge_type = ?")
            params.append(edge_type)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self._con.execute(
            f"SELECT * FROM edges {where} ORDER BY edge_id",  # noqa: S608
            params,
        ).fetchall()
        cols = self._edge_columns()
        return [self._row_to_dict(r, cols) for r in rows]

    # ------------------------------------------------------------------
    # Dependency graph traversal
    # ------------------------------------------------------------------

    def get_dependencies(self, file_id: int, transitive: bool = False) -> list[dict]:
        """Return files that file_id depends on (its imports).

        Non-transitive: direct edges only (depth 1).
        Transitive: recursive walk downward; each result includes 'depth'.
        """
        if not transitive:
            rows = self._con.execute(
                """
                SELECT f.*, 1 AS depth
                FROM edges e
                JOIN files f ON e.target_file_id = f.file_id
                WHERE e.source_file_id = ?
                  AND e.edge_type = 'imports'
                  AND e.target_file_id IS NOT NULL
                ORDER BY f.file_id
                """,
                [file_id],
            ).fetchall()
            cols = self._file_columns() + ["depth"]
            return [self._row_to_dict(r, cols) for r in rows]

        # Transitive: recursive CTE with depth limit for cycle safety.
        # DISTINCT on (file_id, depth) inside the CTE lets us expand all paths,
        # then we take MIN(depth) per file so each file appears once.
        rows = self._con.execute(
            f"""
            WITH RECURSIVE deps(file_id, depth) AS (
                SELECT e.target_file_id, 1
                FROM edges e
                WHERE e.source_file_id = ?
                  AND e.edge_type = 'imports'
                  AND e.target_file_id IS NOT NULL

                UNION ALL

                SELECT e.target_file_id, d.depth + 1
                FROM deps d
                JOIN edges e ON d.file_id = e.source_file_id
                WHERE e.edge_type = 'imports'
                  AND e.target_file_id IS NOT NULL
                  AND d.depth < {_MAX_DEPTH}
            )
            SELECT f.*, MIN(d.depth) AS depth
            FROM (SELECT DISTINCT file_id, depth FROM deps) d
            JOIN files f ON d.file_id = f.file_id
            GROUP BY
                f.file_id, f.path, f.language, f.size_bytes,
                f.line_count, f.hash, f.indexed_at
            ORDER BY MIN(d.depth), f.file_id
            """,
            [file_id],
        ).fetchall()
        cols = self._file_columns() + ["depth"]
        return [self._row_to_dict(r, cols) for r in rows]

    def get_dependents(self, file_id: int, transitive: bool = False) -> list[dict]:
        """Return files that depend on (import) file_id.

        Non-transitive: direct edges only (depth 1).
        Transitive: recursive walk upward; each result includes 'depth'.
        """
        if not transitive:
            rows = self._con.execute(
                """
                SELECT f.*, 1 AS depth
                FROM edges e
                JOIN files f ON e.source_file_id = f.file_id
                WHERE e.target_file_id = ?
                  AND e.edge_type = 'imports'
                ORDER BY f.file_id
                """,
                [file_id],
            ).fetchall()
            cols = self._file_columns() + ["depth"]
            return [self._row_to_dict(r, cols) for r in rows]

        # Walk backwards: who imports file_id, recursively
        rows = self._con.execute(
            f"""
            WITH RECURSIVE deps(file_id, depth) AS (
                SELECT e.source_file_id, 1
                FROM edges e
                WHERE e.target_file_id = ?
                  AND e.edge_type = 'imports'

                UNION ALL

                SELECT e.source_file_id, d.depth + 1
                FROM deps d
                JOIN edges e ON d.file_id = e.target_file_id
                WHERE e.edge_type = 'imports'
                  AND d.depth < {_MAX_DEPTH}
            )
            SELECT f.*, MIN(d.depth) AS depth
            FROM (SELECT DISTINCT file_id, depth FROM deps) d
            JOIN files f ON d.file_id = f.file_id
            GROUP BY
                f.file_id, f.path, f.language, f.size_bytes,
                f.line_count, f.hash, f.indexed_at
            ORDER BY MIN(d.depth), f.file_id
            """,
            [file_id],
        ).fetchall()
        cols = self._file_columns() + ["depth"]
        return [self._row_to_dict(r, cols) for r in rows]

    # ------------------------------------------------------------------
    # Import operations
    # ------------------------------------------------------------------

    def upsert_import(self, record: ImportRecord) -> int:
        """Insert an import declaration row.  Returns the import_id."""
        row = self._con.execute(
            """
            INSERT INTO imports(
                file_id, module_path, imported_names, alias,
                is_relative, line_number, resolved_file_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            RETURNING import_id
            """,
            [
                record.file_id,
                record.module_path,
                record.imported_names,
                record.alias,
                record.is_relative,
                record.line_number,
                record.resolved_file_id,
            ],
        ).fetchone()
        assert row is not None
        return int(row[0])

    def resolve_import(self, import_id: int, resolved_file_id: int) -> None:
        """Set resolved_file_id on an import row once the target is known."""
        self._con.execute(
            "UPDATE imports SET resolved_file_id = ? WHERE import_id = ?",
            [resolved_file_id, import_id],
        )

    def get_imports(self, file_id: int | None = None) -> list[dict]:
        """Return import rows, optionally filtered to a specific file."""
        if file_id is not None:
            rows = self._con.execute(
                "SELECT * FROM imports WHERE file_id = ? ORDER BY import_id",
                [file_id],
            ).fetchall()
        else:
            rows = self._con.execute(
                "SELECT * FROM imports ORDER BY import_id"
            ).fetchall()
        cols = self._import_columns()
        return [self._row_to_dict(r, cols) for r in rows]

    # ------------------------------------------------------------------
    # Metadata key/value store
    # ------------------------------------------------------------------

    def set_meta(self, key: str, value: str) -> None:
        """Persist a key/value metadata entry, creating or replacing it."""
        self._con.execute(
            """
            INSERT INTO palace_meta(key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value      = excluded.value,
                updated_at = NOW()
            """,
            [key, value],
        )

    def get_meta(self, key: str) -> str | None:
        """Return the stored value for key, or None if not found."""
        row = self._con.execute(
            "SELECT value FROM palace_meta WHERE key = ?",
            [key],
        ).fetchone()
        return str(row[0]) if row is not None else None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Delete all rows from every table, preserving the schema and sequences.

        DuckDB evaluates FK constraints per-row using the **original** table snapshot,
        not the mid-statement state.  This means a single
        ``DELETE FROM symbols`` (or even ``UPDATE … SET parent_id = NULL`` followed by
        ``DELETE``) fails whenever the symbols table contains a multi-level
        parent_id chain, because DuckDB sees the not-yet-deleted child row when it
        validates the FK for the parent row being deleted.

        The correct approach is an iterative **leaf-first** deletion: each pass
        removes symbol rows that are not referenced by any remaining row's parent_id,
        shrinking the tree from the outside in.  Two or three passes are sufficient
        for typical code hierarchies (module → class → method).

        Deletion order respects the FK dependency graph:
          palace_meta → imports → edges → symbols (leaf-first loop) → files
        """
        # Tables with no inbound FKs from other user tables — safe to clear first.
        self._con.execute("DELETE FROM palace_meta")
        # imports references files only; clearing before symbols avoids FK conflicts.
        self._con.execute("DELETE FROM imports")
        # edges references both files and symbols; must clear before symbols.
        self._con.execute("DELETE FROM edges")
        # Leaf-first loop: each iteration removes symbol rows that are no longer
        # referenced by any other symbol's parent_id.  Runs until the table is empty.
        # This handles arbitrarily deep parent_id chains without disabling FK checks.
        while self._con.execute("SELECT COUNT(*) FROM symbols").fetchone()[0] > 0:
            self._con.execute(
                """
                DELETE FROM symbols
                WHERE symbol_id NOT IN (
                    SELECT DISTINCT parent_id FROM symbols WHERE parent_id IS NOT NULL
                )
                """
            )
        # No table references files after the above deletions.
        self._con.execute("DELETE FROM files")

    def close(self) -> None:
        """Close the underlying DuckDB connection."""
        self._con.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _file_columns() -> list[str]:
        return ["file_id", "path", "language", "size_bytes", "line_count", "hash", "indexed_at"]

    @staticmethod
    def _symbol_columns() -> list[str]:
        return [
            "symbol_id", "file_id", "name", "qualified_name", "kind",
            "line_start", "line_end", "col_start", "col_end",
            "parent_id", "signature", "docstring", "is_exported", "metadata",
        ]

    @staticmethod
    def _edge_columns() -> list[str]:
        return [
            "edge_id", "source_file_id", "target_file_id",
            "source_symbol_id", "target_symbol_id",
            "edge_type", "weight", "metadata",
        ]

    @staticmethod
    def _import_columns() -> list[str]:
        return [
            "import_id", "file_id", "module_path", "imported_names",
            "alias", "is_relative", "line_number", "resolved_file_id",
        ]

    @staticmethod
    def _row_to_dict(row: tuple, columns: list[str]) -> dict:
        """Zip a result tuple with its column names into a plain dict."""
        return dict(zip(columns, row))
