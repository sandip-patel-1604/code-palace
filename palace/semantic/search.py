"""Semantic search — thin wrapper that embeds a query and delegates to VectorStore."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from palace.semantic.embeddings import EmbeddingEngine, MockEmbeddingEngine
    from palace.storage.vector_store import LanceDBVectorStore


class SemanticSearch:
    """Vector similarity search over the indexed codebase.

    Acts as the single entry-point for natural-language queries: it converts
    free-form text into an embedding vector and forwards the vector to the
    appropriate VectorStore search method.

    Designed for graceful degradation — if either dependency (store or engine)
    was not configured (e.g. the user has not run the index command yet), every
    search call returns an empty list rather than raising.
    """

    def __init__(
        self,
        vector_store: LanceDBVectorStore | None,
        engine: MockEmbeddingEngine | EmbeddingEngine | None,
    ) -> None:
        # Both dependencies are optional so that callers can construct the
        # object unconditionally and check .available() before querying.
        self._store = vector_store
        self._engine = engine

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def available(self) -> bool:
        """Return True if both vector store and engine are configured.

        Callers should check this before showing search UI elements — there is
        no point prompting the user for a query if the store is empty or the
        embedding engine was never set up.
        """
        return self._store is not None and self._engine is not None

    def search(
        self,
        query: str,
        limit: int = 20,
        kind: str | None = None,
        language: str | None = None,
        mode: str = "symbols",
    ) -> list[dict]:
        """Search for symbols or files matching a natural-language query.

        The flow is: embed query text → call the appropriate vector store
        search method → return results.  Splitting into two modes lets callers
        choose whether they want symbol-level (name, kind, qualified_name) or
        file-level (path, language) results from the same interface.

        Args:
            query: Natural language search text.
            limit: Maximum number of results to return.
            kind: Filter by symbol kind (only applied when mode="symbols").
            language: Filter by language (only applied when mode="files").
            mode: "symbols" to search symbol embeddings, "files" for file
                  embeddings.

        Returns:
            List of result dicts with score and relevant metadata.
            Returns [] if vector_store or engine is None, or query is empty.
        """
        # Graceful degradation: missing dependencies or empty input → no results.
        if not self.available():
            return []
        if not query:
            return []

        # TYPE_CHECKING guard means _engine / _store are typed as None in the
        # else branch; assert after the available() check is the idiomatic way
        # to tell the type checker they are non-None here.
        assert self._engine is not None
        assert self._store is not None

        query_vector: list[float] = self._engine.embed(query)

        if mode == "files":
            return self._store.search_files(query_vector, limit=limit, language=language)

        # Default: symbol search.  Unknown mode values fall through to symbols
        # rather than raising, keeping the public contract forgiving.
        return self._store.search_symbols(query_vector, limit=limit, kind=kind)
