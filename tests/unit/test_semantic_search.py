"""T_10 gate tests — SemanticSearch validation."""

from __future__ import annotations

import pytest

from palace.semantic.embeddings import MockEmbeddingEngine
from palace.semantic.search import SemanticSearch
from palace.storage.vector_store import LanceDBVectorStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_symbols(store: LanceDBVectorStore, engine: MockEmbeddingEngine) -> None:
    """Insert a small set of symbol embeddings with mixed kinds.

    Using the engine to produce vectors ensures that search queries run
    through the same engine will find these rows (deterministic SHA-256
    vectors are consistent across calls).
    """
    symbols = [
        (1, 10, "AuthService",  "app.auth.AuthService",  "class",    "app/auth.py",    "class AuthService"),
        (2, 10, "authenticate", "app.auth.authenticate", "function", "app/auth.py",    "def authenticate"),
        (3, 11, "UserModel",    "app.models.UserModel",  "class",    "app/models.py",  "class UserModel"),
        (4, 11, "save_user",    "app.models.save_user",  "function", "app/models.py",  "def save_user"),
    ]
    for symbol_id, file_id, name, qualified_name, kind, file_path, text in symbols:
        store.upsert_symbol_embedding(
            symbol_id, file_id, name, qualified_name, kind, file_path, text,
            engine.embed(text),
        )


# ---------------------------------------------------------------------------
# T_10 — SemanticSearch
# ---------------------------------------------------------------------------


class TestSemanticSearch:
    def test_search_with_results(self, tmp_path: pytest.TempPathFactory) -> None:
        """T_11.1: insert embeddings via MockEngine + LanceDB, search returns non-empty results with correct keys."""
        store = LanceDBVectorStore(str(tmp_path))
        engine = MockEmbeddingEngine()
        _insert_symbols(store, engine)

        searcher = SemanticSearch(store, engine)
        results = searcher.search("class AuthService", limit=10)

        assert len(results) > 0
        # Every result must carry the full set of expected symbol keys.
        required_keys = {"symbol_id", "file_id", "name", "qualified_name", "kind", "file_path", "score"}
        for row in results:
            assert required_keys == set(row.keys())

        # Score is 1 - L2_distance; the top (exact-match) result should be ~1.0.
        # Other rows may score below 0.0 for dissimilar vectors under L2, so we
        # only bound the top result — that is what the VectorStore contract
        # already guarantees for an exact-match query.
        assert results[0]["score"] == pytest.approx(1.0, abs=1e-4)

        store.close()

    def test_empty_store(self, tmp_path: pytest.TempPathFactory) -> None:
        """T_11.1: search on an empty vector store returns [] without raising."""
        store = LanceDBVectorStore(str(tmp_path))
        engine = MockEmbeddingEngine()

        searcher = SemanticSearch(store, engine)
        # No rows inserted — VectorStore.search_symbols returns [] for empty tables.
        results = searcher.search("anything", limit=10)

        assert results == []

        store.close()

    def test_none_store(self) -> None:
        """T_11.1: vector_store=None makes search return [] (graceful degradation)."""
        engine = MockEmbeddingEngine()
        searcher = SemanticSearch(None, engine)

        results = searcher.search("some query")

        assert results == []
        # available() must report False when store is absent.
        assert searcher.available() is False

    def test_none_engine(self, tmp_path: pytest.TempPathFactory) -> None:
        """T_11.1: engine=None makes search return [] (graceful degradation)."""
        store = LanceDBVectorStore(str(tmp_path))
        searcher = SemanticSearch(store, None)

        results = searcher.search("some query")

        assert results == []
        assert searcher.available() is False

        store.close()

    def test_empty_query(self, tmp_path: pytest.TempPathFactory) -> None:
        """T_11.1: empty query string returns [] without calling the engine."""
        store = LanceDBVectorStore(str(tmp_path))
        engine = MockEmbeddingEngine()
        _insert_symbols(store, engine)

        searcher = SemanticSearch(store, engine)
        results = searcher.search("")

        assert results == []

        store.close()

    def test_kind_filter(self, tmp_path: pytest.TempPathFactory) -> None:
        """T_11.1: insert mixed kinds, search with kind='class' returns only class results."""
        store = LanceDBVectorStore(str(tmp_path))
        engine = MockEmbeddingEngine()
        _insert_symbols(store, engine)

        searcher = SemanticSearch(store, engine)
        results = searcher.search("user model class", limit=10, kind="class")

        assert len(results) > 0
        # Every returned row must be a class — functions must not bleed through.
        for row in results:
            assert row["kind"] == "class"

        store.close()

    def test_available_both_set(self, tmp_path: pytest.TempPathFactory) -> None:
        """T_11.1: available() is True only when both store and engine are non-None."""
        store = LanceDBVectorStore(str(tmp_path))
        engine = MockEmbeddingEngine()

        assert SemanticSearch(store, engine).available() is True
        assert SemanticSearch(None, engine).available() is False
        assert SemanticSearch(store, None).available() is False
        assert SemanticSearch(None, None).available() is False

        store.close()

    def test_file_mode_search(self, tmp_path: pytest.TempPathFactory) -> None:
        """T_11.1: mode='files' delegates to search_files and returns file-level keys."""
        store = LanceDBVectorStore(str(tmp_path))
        engine = MockEmbeddingEngine()

        # Insert a couple of file embeddings.
        store.upsert_file_embedding(1, "app/auth.py",   "python", "auth module",   engine.embed("auth module"))
        store.upsert_file_embedding(2, "app/models.py", "python", "models module", engine.embed("models module"))

        searcher = SemanticSearch(store, engine)
        results = searcher.search("auth module", mode="files", limit=5)

        assert len(results) > 0
        required_keys = {"file_id", "path", "language", "score"}
        for row in results:
            assert required_keys == set(row.keys())

        store.close()
