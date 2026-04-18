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
            # ----- Phase 2 tables -----
            # domains
            "CREATE SEQUENCE IF NOT EXISTS domain_id_seq START 1",
            """
            CREATE TABLE IF NOT EXISTS domains (
                domain_id    INTEGER PRIMARY KEY DEFAULT nextval('domain_id_seq'),
                name         TEXT    NOT NULL,
                description  TEXT,
                color        TEXT,
                metadata     JSON
            )
            """,
            # file → domain assignment (composite PK, no surrogate)
            """
            CREATE TABLE IF NOT EXISTS file_domains (
                file_id      INTEGER NOT NULL REFERENCES files(file_id),
                domain_id    INTEGER NOT NULL REFERENCES domains(domain_id),
                confidence   FLOAT   DEFAULT 1.0,
                PRIMARY KEY (file_id, domain_id)
            )
            """,
            # git commit history (committer date for temporal ordering)
            "CREATE SEQUENCE IF NOT EXISTS commit_id_seq START 1",
            """
            CREATE TABLE IF NOT EXISTS git_commits (
                commit_id    INTEGER PRIMARY KEY DEFAULT nextval('commit_id_seq'),
                sha          TEXT    NOT NULL UNIQUE,
                author_name  TEXT    NOT NULL,
                author_email TEXT    NOT NULL,
                committed_at TIMESTAMP NOT NULL,
                message      TEXT,
                insertions   INTEGER DEFAULT 0,
                deletions    INTEGER DEFAULT 0
            )
            """,
            # per-file changes within each commit
            """
            CREATE TABLE IF NOT EXISTS git_file_changes (
                commit_id    INTEGER NOT NULL REFERENCES git_commits(commit_id),
                file_id      INTEGER REFERENCES files(file_id),
                file_path    TEXT    NOT NULL,
                insertions   INTEGER,
                deletions    INTEGER,
                change_type  TEXT    NOT NULL,
                UNIQUE (commit_id, file_path)
            )
            """,
            # materialized co-change pairs (canonical: file_id_a < file_id_b)
            """
            CREATE TABLE IF NOT EXISTS cochange_pairs (
                file_id_a    INTEGER NOT NULL REFERENCES files(file_id),
                file_id_b    INTEGER NOT NULL REFERENCES files(file_id),
                co_commits   INTEGER NOT NULL,
                confidence   FLOAT   NOT NULL,
                PRIMARY KEY (file_id_a, file_id_b),
                CHECK (file_id_a < file_id_b)
            )
            """,
            # Phase 2 indexes
            "CREATE INDEX IF NOT EXISTS idx_file_domains_file   ON file_domains(file_id)",
            "CREATE INDEX IF NOT EXISTS idx_file_domains_domain ON file_domains(domain_id)",
            "CREATE INDEX IF NOT EXISTS idx_commits_sha         ON git_commits(sha)",
            "CREATE INDEX IF NOT EXISTS idx_commits_author      ON git_commits(author_email)",
            "CREATE INDEX IF NOT EXISTS idx_file_changes_commit ON git_file_changes(commit_id)",
            "CREATE INDEX IF NOT EXISTS idx_file_changes_file   ON git_file_changes(file_id)",
            "CREATE INDEX IF NOT EXISTS idx_file_changes_path   ON git_file_changes(file_path)",
            "CREATE INDEX IF NOT EXISTS idx_cochange_a          ON cochange_pairs(file_id_a)",
            "CREATE INDEX IF NOT EXISTS idx_cochange_b          ON cochange_pairs(file_id_b)",
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

    def get_file_by_id(self, file_id: int) -> dict | None:
        """Return the file row for file_id, or None if not found."""
        cols = self._file_columns()
        row = self._con.execute(
            f"SELECT {', '.join(cols)} FROM files WHERE file_id = ?",
            [file_id],
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row, cols)

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

    def upsert_symbols_batch(self, records: list[SymbolRecord]) -> list[int]:
        """Insert multiple symbol rows.  Returns symbol_ids.

        Uses individual INSERTs with RETURNING (DuckDB auto-commits each).
        Reduces Python-side overhead vs calling upsert_symbol in a loop.
        """
        if not records:
            return []
        return [self.upsert_symbol(r) for r in records]

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

    def upsert_edges_batch(self, records: list[EdgeRecord]) -> None:
        """Insert multiple edge rows in a single transaction."""
        if not records:
            return
        params = []
        for record in records:
            metadata_json = json.dumps(record.metadata) if record.metadata is not None else None
            params.append((
                record.source_file_id,
                record.target_file_id,
                record.source_symbol_id,
                record.target_symbol_id,
                record.edge_type,
                record.weight,
                metadata_json,
            ))
        self._con.executemany(
            """
            INSERT INTO edges(
                source_file_id, target_file_id,
                source_symbol_id, target_symbol_id,
                edge_type, weight, metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            params,
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

    def upsert_imports_batch(self, records: list[ImportRecord]) -> list[int]:
        """Insert multiple import rows.  Returns import_ids."""
        if not records:
            return []
        return [self.upsert_import(r) for r in records]

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
        # Phase 2 tables — clear dependents before parents.
        self._con.execute("DELETE FROM cochange_pairs")
        self._con.execute("DELETE FROM git_file_changes")
        self._con.execute("DELETE FROM git_commits")
        self._con.execute("DELETE FROM file_domains")
        self._con.execute("DELETE FROM domains")
        # Phase 1 tables — existing order preserved.
        self._con.execute("DELETE FROM palace_meta")
        self._con.execute("DELETE FROM imports")
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

    # ------------------------------------------------------------------
    # Temporal operations (git history, co-change, ownership, churn)
    # ------------------------------------------------------------------

    def upsert_commit(
        self,
        sha: str,
        author_name: str,
        author_email: str,
        committed_at: str,
        message: str,
        insertions: int,
        deletions: int,
    ) -> int:
        """Insert a git commit. Returns the commit_id."""
        row = self._con.execute(
            """
            INSERT INTO git_commits(sha, author_name, author_email, committed_at,
                                    message, insertions, deletions)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sha) DO UPDATE SET
                author_name  = excluded.author_name,
                author_email = excluded.author_email,
                committed_at = excluded.committed_at,
                message      = excluded.message,
                insertions   = excluded.insertions,
                deletions    = excluded.deletions
            RETURNING commit_id
            """,
            [sha, author_name, author_email, committed_at, message, insertions, deletions],
        ).fetchone()
        assert row is not None
        return int(row[0])

    def upsert_file_change(
        self,
        commit_id: int,
        file_path: str,
        file_id: int | None,
        insertions: int | None,
        deletions: int | None,
        change_type: str,
    ) -> None:
        """Insert a per-file change within a commit."""
        self._con.execute(
            """
            INSERT INTO git_file_changes(commit_id, file_id, file_path,
                                         insertions, deletions, change_type)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(commit_id, file_path) DO UPDATE SET
                file_id     = excluded.file_id,
                insertions  = excluded.insertions,
                deletions   = excluded.deletions,
                change_type = excluded.change_type
            """,
            [commit_id, file_id, file_path, insertions, deletions, change_type],
        )

    def materialize_cochange(self, min_co_commits: int = 3) -> int:
        """Compute cochange_pairs from git_file_changes. Returns pair count.

        Only considers files that exist in the current index (file_id IS NOT NULL).
        Clears existing pairs before recomputing.
        """
        self._con.execute("DELETE FROM cochange_pairs")
        self._con.execute(
            """
            INSERT INTO cochange_pairs(file_id_a, file_id_b, co_commits, confidence)
            SELECT
                LEAST(a.file_id, b.file_id)    AS file_id_a,
                GREATEST(a.file_id, b.file_id)  AS file_id_b,
                COUNT(DISTINCT a.commit_id)      AS co_commits,
                -- Jaccard: co-commits / (commits_a + commits_b - co-commits)
                CAST(COUNT(DISTINCT a.commit_id) AS FLOAT) /
                    NULLIF(ca.total + cb.total - COUNT(DISTINCT a.commit_id), 0)
                    AS confidence
            FROM git_file_changes a
            JOIN git_file_changes b
                ON a.commit_id = b.commit_id
                AND a.file_id < b.file_id
            JOIN (
                SELECT file_id, COUNT(DISTINCT commit_id) AS total
                FROM git_file_changes WHERE file_id IS NOT NULL
                GROUP BY file_id
            ) ca ON ca.file_id = a.file_id
            JOIN (
                SELECT file_id, COUNT(DISTINCT commit_id) AS total
                FROM git_file_changes WHERE file_id IS NOT NULL
                GROUP BY file_id
            ) cb ON cb.file_id = b.file_id
            WHERE a.file_id IS NOT NULL AND b.file_id IS NOT NULL
            GROUP BY LEAST(a.file_id, b.file_id), GREATEST(a.file_id, b.file_id),
                     ca.total, cb.total
            HAVING COUNT(DISTINCT a.commit_id) >= ?
            """,
            [min_co_commits],
        )
        row = self._con.execute("SELECT COUNT(*) FROM cochange_pairs").fetchone()
        return int(row[0]) if row else 0

    def get_cochange_pairs(self, file_id: int, min_co_commits: int = 3) -> list[dict]:
        """Return files that frequently change alongside file_id."""
        rows = self._con.execute(
            """
            SELECT
                CASE WHEN file_id_a = ? THEN file_id_b ELSE file_id_a END AS partner_id,
                co_commits, confidence
            FROM cochange_pairs
            WHERE (file_id_a = ? OR file_id_b = ?)
              AND co_commits >= ?
            ORDER BY co_commits DESC
            """,
            [file_id, file_id, file_id, min_co_commits],
        ).fetchall()
        return [
            {"partner_id": int(r[0]), "co_commits": int(r[1]), "confidence": float(r[2])}
            for r in rows
        ]

    def get_all_cochange_pairs(self, min_co_commits: int = 3) -> list[dict]:
        """Return all cochange pairs above the threshold in one query."""
        rows = self._con.execute(
            """
            SELECT file_id_a, file_id_b, co_commits, confidence
            FROM cochange_pairs
            WHERE co_commits >= ?
            ORDER BY co_commits DESC
            """,
            [min_co_commits],
        ).fetchall()
        return [
            {
                "file_id_a": int(r[0]),
                "file_id_b": int(r[1]),
                "co_commits": int(r[2]),
                "confidence": float(r[3]),
            }
            for r in rows
        ]

    def get_file_ownership(self, file_id: int) -> list[dict]:
        """Return author contribution breakdown for a file."""
        rows = self._con.execute(
            """
            SELECT gc.author_name, gc.author_email,
                   COUNT(*) AS commit_count,
                   SUM(COALESCE(gfc.insertions, 0) + COALESCE(gfc.deletions, 0)) AS lines_changed
            FROM git_file_changes gfc
            JOIN git_commits gc ON gc.commit_id = gfc.commit_id
            WHERE gfc.file_id = ?
            GROUP BY gc.author_name, gc.author_email
            ORDER BY commit_count DESC
            """,
            [file_id],
        ).fetchall()
        return [
            {
                "author_name": r[0],
                "author_email": r[1],
                "commit_count": int(r[2]),
                "lines_changed": int(r[3]),
            }
            for r in rows
        ]

    def get_churn(self, file_id: int | None = None, days: int = 90) -> list[dict]:
        """Return change-frequency metrics within a time window."""
        # DuckDB does not support parameterised INTERVAL, so inline the integer
        # after validating it is a safe positive int.
        safe_days = max(1, int(days))
        conditions = [f"gc.committed_at >= current_timestamp - INTERVAL '{safe_days}' DAY"]
        params: list[object] = []
        if file_id is not None:
            conditions.append("gfc.file_id = ?")
            params.append(file_id)
        else:
            conditions.append("gfc.file_id IS NOT NULL")
        where = " AND ".join(conditions)
        rows = self._con.execute(
            f"""
            SELECT gfc.file_id, COUNT(DISTINCT gfc.commit_id) AS change_count,
                   SUM(COALESCE(gfc.insertions, 0)) AS total_insertions,
                   SUM(COALESCE(gfc.deletions, 0)) AS total_deletions
            FROM git_file_changes gfc
            JOIN git_commits gc ON gc.commit_id = gfc.commit_id
            WHERE {where}
            GROUP BY gfc.file_id
            ORDER BY change_count DESC
            """,  # noqa: S608
            params,
        ).fetchall()
        return [
            {
                "file_id": int(r[0]),
                "change_count": int(r[1]),
                "total_insertions": int(r[2]),
                "total_deletions": int(r[3]),
            }
            for r in rows
        ]

    def get_commit_count(self) -> int:
        """Return total number of stored commits."""
        row = self._con.execute("SELECT COUNT(*) FROM git_commits").fetchone()
        return int(row[0]) if row else 0

    # ------------------------------------------------------------------
    # Domain operations (clustering)
    # ------------------------------------------------------------------

    def upsert_domain(
        self,
        name: str,
        description: str | None = None,
        color: str | None = None,
    ) -> int:
        """Insert a domain cluster. Returns the domain_id."""
        metadata_json = None
        row = self._con.execute(
            """
            INSERT INTO domains(name, description, color, metadata)
            VALUES (?, ?, ?, ?)
            RETURNING domain_id
            """,
            [name, description, color, metadata_json],
        ).fetchone()
        assert row is not None
        return int(row[0])

    def assign_file_to_domain(
        self,
        file_id: int,
        domain_id: int,
        confidence: float = 1.0,
    ) -> None:
        """Map a file to a domain cluster."""
        self._con.execute(
            """
            INSERT INTO file_domains(file_id, domain_id, confidence)
            VALUES (?, ?, ?)
            ON CONFLICT(file_id, domain_id) DO UPDATE SET
                confidence = excluded.confidence
            """,
            [file_id, domain_id, confidence],
        )

    def get_domains(self) -> list[dict]:
        """Return all domain clusters."""
        rows = self._con.execute(
            "SELECT domain_id, name, description, color, metadata FROM domains ORDER BY domain_id"
        ).fetchall()
        return [
            {
                "domain_id": int(r[0]),
                "name": r[1],
                "description": r[2],
                "color": r[3],
                "metadata": r[4],
            }
            for r in rows
        ]

    def get_domain_files(self, domain_id: int) -> list[dict]:
        """Return files assigned to a domain."""
        rows = self._con.execute(
            """
            SELECT f.*, fd.confidence
            FROM file_domains fd
            JOIN files f ON f.file_id = fd.file_id
            WHERE fd.domain_id = ?
            ORDER BY f.file_id
            """,
            [domain_id],
        ).fetchall()
        cols = self._file_columns() + ["confidence"]
        return [self._row_to_dict(r, cols) for r in rows]

    def get_file_domain(self, file_id: int) -> dict | None:
        """Return the domain assignment for a file, or None."""
        row = self._con.execute(
            """
            SELECT d.domain_id, d.name, d.description, d.color, fd.confidence
            FROM file_domains fd
            JOIN domains d ON d.domain_id = fd.domain_id
            WHERE fd.file_id = ?
            """,
            [file_id],
        ).fetchone()
        if row is None:
            return None
        return {
            "domain_id": int(row[0]),
            "name": row[1],
            "description": row[2],
            "color": row[3],
            "confidence": float(row[4]),
        }

    def clear_domains(self) -> None:
        """Delete all domain assignments and domains."""
        self._con.execute("DELETE FROM file_domains")
        self._con.execute("DELETE FROM domains")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

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
