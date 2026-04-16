"""T_9 gate tests — EmbeddingEngine and MockEmbeddingEngine validation."""

from __future__ import annotations

import pytest

from palace.semantic.embeddings import MockEmbeddingEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine() -> MockEmbeddingEngine:
    """Fresh MockEmbeddingEngine instance for each test."""
    return MockEmbeddingEngine()


# ---------------------------------------------------------------------------
# T_9.6 — Single-text embedding
# ---------------------------------------------------------------------------


class TestMockEmbedding:
    """T_9.6 — MockEmbeddingEngine.embed() contract verification."""

    def test_embed_dimension(self, engine: MockEmbeddingEngine) -> None:
        """T_9.6: embed("hello") returns a list of exactly 768 elements."""
        result = engine.embed("hello")
        assert len(result) == 768

    def test_embed_types(self, engine: MockEmbeddingEngine) -> None:
        """T_9.6: all elements of the returned vector are Python floats."""
        result = engine.embed("type check")
        assert all(isinstance(v, float) for v in result)

    def test_embed_determinism(self, engine: MockEmbeddingEngine) -> None:
        """T_9.6: calling embed("x") twice returns identical vectors."""
        first = engine.embed("x")
        second = engine.embed("x")
        assert first == second

    def test_embed_empty(self, engine: MockEmbeddingEngine) -> None:
        """T_9.6: embed("") returns a 768-dim vector without raising."""
        result = engine.embed("")
        assert len(result) == 768
        assert all(isinstance(v, float) for v in result)

    def test_batch_consistency(self, engine: MockEmbeddingEngine) -> None:
        """T_9.6: embed("a") and embed_batch(["a"])[0] return identical vectors."""
        single = engine.embed("a")
        batch = engine.embed_batch(["a"])
        assert single == batch[0]


# ---------------------------------------------------------------------------
# T_9.7 — Batch embedding
# ---------------------------------------------------------------------------


class TestMockEmbedBatch:
    """T_9.7 — MockEmbeddingEngine.embed_batch() contract verification."""

    def test_batch_multiple(self, engine: MockEmbeddingEngine) -> None:
        """T_9.7: embed_batch(["a","b","c"]) returns 3 vectors each of length 768."""
        results = engine.embed_batch(["a", "b", "c"])
        assert len(results) == 3
        for vec in results:
            assert len(vec) == 768

    def test_batch_empty_list(self, engine: MockEmbeddingEngine) -> None:
        """T_9.7: embed_batch([]) returns an empty list without raising."""
        results = engine.embed_batch([])
        assert results == []
