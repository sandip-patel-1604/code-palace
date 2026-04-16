"""High-level Palace orchestrator — parsing, graph building, and storage."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from palace.core.config import PalaceConfig
from palace.graph.builder import BuildStats, GraphBuilder
from palace.parsing.engine import ParsingEngine
from palace.storage.duckdb_store import DuckDBStore


class Palace:
    """High-level API orchestrating parsing, graph building, and storage.

    Lifecycle: create → init() (or open()) → use → close().
    """

    def __init__(self, config: PalaceConfig) -> None:
        self.config = config
        self.store: DuckDBStore | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Open the existing palace database without re-indexing."""
        self.store = DuckDBStore(str(self.config.db_path))
        self.store.initialize_schema()

    def close(self) -> None:
        """Close the database connection if open."""
        if self.store is not None:
            self.store.close()
            self.store = None

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def init(
        self,
        force: bool = False,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> BuildStats:
        """Parse the codebase and build the palace graph.

        Opens (or creates) the database, then runs the three-phase build.
        If force=True, clears existing data before re-indexing.
        progress_callback(done, total) is called after each file is parsed.
        """
        self.store = DuckDBStore(str(self.config.db_path))
        self.store.initialize_schema()

        if force:
            self.store.clear()

        # Detect languages and update config
        lang_counts = self.config.detect_languages()
        self.config.languages = list(lang_counts.keys())
        self.config.save()

        # Parse
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

        return stats


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _now_iso() -> str:
    """Return the current UTC timestamp as an ISO-8601 string."""
    from datetime import datetime, timezone

    return datetime.now(tz=timezone.utc).isoformat()
