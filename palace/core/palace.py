"""High-level Palace orchestrator — parsing, graph building, and storage."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from palace.core.config import PalaceConfig
from palace.core.logging import get_logger
from palace.graph.builder import BuildStats, GraphBuilder
from palace.parsing.engine import ParsingEngine
from palace.storage.duckdb_store import DuckDBStore

logger = get_logger(__name__)


class Palace:
    """High-level API orchestrating parsing, graph building, and storage.

    Lifecycle: create → init() (or open()) → use → close().
    """

    def __init__(self, config: PalaceConfig) -> None:
        self.config = config
        self.store: DuckDBStore | None = None
        self.vector_store = None  # LanceDBVectorStore | None, imported lazily

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Open the existing palace database without re-indexing."""
        self.store = DuckDBStore(str(self.config.db_path))
        self.store.initialize_schema()
        # Conditionally open vector store if it has been created already
        if self.config.vectors_dir.exists():
            from palace.storage.vector_store import LanceDBVectorStore
            self.vector_store = LanceDBVectorStore(str(self.config.vectors_dir))

    def close(self) -> None:
        """Close the database connection if open."""
        if self.store is not None:
            self.store.close()
            self.store = None
        if self.vector_store is not None:
            self.vector_store.close()
            self.vector_store = None

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def init(
        self,
        force: bool = False,
        skip_git: bool = False,
        skip_embeddings: bool = False,
        skip_domains: bool = False,
        git_depth: int = 10_000,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> BuildStats:
        """Parse the codebase and build the palace graph.

        Opens (or creates) the database, then runs the build phases:
          Phase 1 — parse files and build symbol graph (always runs)
          Phase 2 — git history ingestion (skip with skip_git=True)
          Phase 3 — symbol embeddings via MockEmbeddingEngine (skip with skip_embeddings=True)
          Phase 4 — domain clustering stub (skip with skip_domains=True)

        If force=True, clears existing data and wipes the vectors dir before re-indexing.
        progress_callback(done, total) is called after each file is parsed.
        """
        self.store = DuckDBStore(str(self.config.db_path))
        self.store.initialize_schema()

        if force:
            self.store.clear()
            # Wipe and recreate the vectors directory so stale embeddings are gone
            if self.config.vectors_dir.exists():
                shutil.rmtree(self.config.vectors_dir)
            self.config.vectors_dir.mkdir(parents=True, exist_ok=True)

        # Detect languages and update config
        lang_counts = self.config.detect_languages()
        self.config.languages = list(lang_counts.keys())
        self.config.save()

        # --- Phase 1: Parse and build graph ---
        engine = ParsingEngine()
        extractions = engine.parse_all(
            self.config.root,
            exclude=self.config.exclude_patterns,
        )

        # Notify caller of progress (one shot at completion — engine parses eagerly)
        if progress_callback is not None:
            total = len(extractions)
            progress_callback(total, total)

        # Store metadata
        self.store.set_meta("root", str(self.config.root))
        self.store.set_meta("indexed_at", _now_iso())

        # Build graph
        builder = GraphBuilder(self.store)
        stats = builder.build(extractions, self.config.root)

        # --- Phase 2: Git history ---
        git_analyzed = False
        if not skip_git:
            try:
                from palace.temporal.history import GitHistory
                count = GitHistory(self.config.root).ingest(self.store, git_depth)
                stats.commits = count
                git_analyzed = True
            except Exception as exc:  # noqa: BLE001
                logger.warning("Git history ingestion failed: %s", exc)
                stats.errors.append(f"git: {exc}")

        # --- Phase 3: Embeddings ---
        embeddings_computed = False
        if not skip_embeddings:
            try:
                from palace.semantic.embeddings import MockEmbeddingEngine
                from palace.storage.vector_store import LanceDBVectorStore

                # Ensure vectors directory exists
                self.config.vectors_dir.mkdir(parents=True, exist_ok=True)
                self.vector_store = LanceDBVectorStore(str(self.config.vectors_dir))

                symbols = self.store.get_symbols()
                engine_emb = MockEmbeddingEngine()
                count = 0
                for sym in symbols:
                    text = (
                        f"{sym['name']} "
                        f"{sym.get('signature') or ''} "
                        f"{sym.get('docstring') or ''}"
                    ).strip()
                    vector = engine_emb.embed(text)
                    self.vector_store.upsert_symbol_embedding(
                        symbol_id=sym["symbol_id"],
                        file_id=sym["file_id"],
                        name=sym["name"],
                        qualified_name=sym["qualified_name"],
                        kind=sym["kind"],
                        file_path=_file_path_by_id(sym["file_id"], self.store),
                        text=text,
                        vector=vector,
                    )
                    count += 1
                stats.embeddings = count
                embeddings_computed = True
            except Exception as exc:  # noqa: BLE001
                logger.warning("Embedding computation failed: %s", exc)
                stats.errors.append(f"embeddings: {exc}")

        # --- Phase 4: Domain clustering (stub — full impl in Phase 2.2) ---
        domains_computed = False
        if not skip_domains:
            try:
                stats.domains = 0
                domains_computed = True
            except Exception as exc:  # noqa: BLE001
                logger.warning("Domain clustering failed: %s", exc)
                stats.errors.append(f"domains: {exc}")

        # Persist phase completion flags to palace_meta
        self.store.set_meta("git_analyzed", str(git_analyzed).lower())
        self.store.set_meta("embeddings_computed", str(embeddings_computed).lower())
        self.store.set_meta("domains_computed", str(domains_computed).lower())

        return stats


# ------------------------------------------------------------------
# Private helpers
# ------------------------------------------------------------------

def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(tz=timezone.utc).isoformat()


def _file_path_by_id(file_id: int, store: DuckDBStore) -> str:
    """Return the file path string for a given file_id via O(1) index lookup."""
    row = store.get_file_by_id(file_id)
    if row is None:
        return ""
    return row.get("path", "")
