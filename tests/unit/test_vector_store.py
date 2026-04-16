"""T_9 gate tests — LanceDB Vector Store validation."""

from __future__ import annotations

import hashlib

import pytest

from palace.storage.vector_store import LanceDBVectorStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_vector(seed: str) -> list[float]:
    """Return a deterministic 768-dim float32 vector derived from seed.

    Using sha256 repeated bytes ensures the vector is uniquely determined by
    the seed string and is cheap to compute in tests without any ML model.
    """
    digest = hashlib.sha256(seed.encode()).digest()
    # digest is 32 bytes; repeat until we have >=768 values then slice.
    repeated = (digest * 24)[:768]
    return [float(b) / 255.0 for b in repeated]


# ---------------------------------------------------------------------------
# T_9.3 — Symbol embeddings
# ---------------------------------------------------------------------------


class TestSymbolEmbeddings:
    def test_upsert_and_search(self, tmp_path: pytest.TempPathFactory) -> None:
        """T_9.3: insert 3 symbol embeddings, search, verify correct keys returned."""
        store = LanceDBVectorStore(str(tmp_path))

        store.upsert_symbol_embedding(1, 10, "foo", "module.foo", "function", "a.py", "def foo", _make_vector("foo"))
        store.upsert_symbol_embedding(2, 10, "bar", "module.bar", "class",    "a.py", "class bar", _make_vector("bar"))
        store.upsert_symbol_embedding(3, 11, "baz", "module.baz", "function", "b.py", "def baz", _make_vector("baz"))

        results = store.search_symbols(_make_vector("foo"), limit=5)

        assert len(results) > 0
        # Every result must carry the full set of expected keys.
        required_keys = {"symbol_id", "file_id", "name", "qualified_name", "kind", "file_path", "score"}
        for row in results:
            assert required_keys == set(row.keys())

        # The top result should be symbol_id=1 (exact match on the query vector).
        top = results[0]
        assert top["symbol_id"] == 1
        assert top["name"] == "foo"
        assert 0.0 <= top["score"] <= 1.0

        store.close()

    def test_upsert_idempotency(self, tmp_path: pytest.TempPathFactory) -> None:
        """T_9.3: inserting the same symbol_id twice keeps exactly one row."""
        store = LanceDBVectorStore(str(tmp_path))

        store.upsert_symbol_embedding(42, 5, "alpha", "pkg.alpha", "function", "x.py", "def alpha", _make_vector("alpha"))
        # Second upsert — same symbol_id, different text/vector.
        store.upsert_symbol_embedding(42, 5, "alpha", "pkg.alpha", "function", "x.py", "def alpha v2", _make_vector("alpha_v2"))

        results = store.search_symbols(_make_vector("alpha_v2"), limit=10)
        ids = [r["symbol_id"] for r in results]

        # Only one row should exist for symbol_id=42.
        assert ids.count(42) == 1

        store.close()

    def test_kind_filter(self, tmp_path: pytest.TempPathFactory) -> None:
        """T_9.3: kind filter restricts results to the requested kind only."""
        store = LanceDBVectorStore(str(tmp_path))

        store.upsert_symbol_embedding(1, 1, "MyClass",  "mod.MyClass",  "class",    "c.py", "class MyClass", _make_vector("MyClass"))
        store.upsert_symbol_embedding(2, 1, "my_func",  "mod.my_func",  "function", "c.py", "def my_func", _make_vector("my_func"))
        store.upsert_symbol_embedding(3, 1, "OtherClass", "mod.OtherClass", "class", "c.py", "class OtherClass", _make_vector("OtherClass"))

        results = store.search_symbols(_make_vector("MyClass"), limit=10, kind="class")

        assert len(results) > 0
        # Every returned row must be a class.
        for row in results:
            assert row["kind"] == "class"
        # Functions must not appear.
        assert all(r["kind"] != "function" for r in results)

        store.close()


# ---------------------------------------------------------------------------
# T_9.4 — File embeddings
# ---------------------------------------------------------------------------


class TestFileEmbeddings:
    def test_upsert_and_search(self, tmp_path: pytest.TempPathFactory) -> None:
        """T_9.4: insert 3 file embeddings, search, verify correct keys returned."""
        store = LanceDBVectorStore(str(tmp_path))

        store.upsert_file_embedding(1, "src/main.py",  "python",     "main module",   _make_vector("main.py"))
        store.upsert_file_embedding(2, "src/utils.py", "python",     "utility funcs", _make_vector("utils.py"))
        store.upsert_file_embedding(3, "src/main.go",  "go",         "go entrypoint", _make_vector("main.go"))

        results = store.search_files(_make_vector("main.py"), limit=5)

        assert len(results) > 0
        required_keys = {"file_id", "path", "language", "score"}
        for row in results:
            assert required_keys == set(row.keys())

        top = results[0]
        assert top["file_id"] == 1
        assert top["path"] == "src/main.py"
        assert 0.0 <= top["score"] <= 1.0

        store.close()

    def test_language_filter(self, tmp_path: pytest.TempPathFactory) -> None:
        """T_9.4: language filter restricts results to the requested language only."""
        store = LanceDBVectorStore(str(tmp_path))

        store.upsert_file_embedding(1, "a.py", "python", "python file", _make_vector("a.py"))
        store.upsert_file_embedding(2, "b.py", "python", "python file", _make_vector("b.py"))
        store.upsert_file_embedding(3, "c.go", "go",     "go file",     _make_vector("c.go"))

        results = store.search_files(_make_vector("a.py"), limit=10, language="python")

        assert len(results) > 0
        for row in results:
            assert row["language"] == "python"
        # Go file must not appear.
        assert all(r["language"] != "go" for r in results)

        store.close()


# ---------------------------------------------------------------------------
# T_9.5 — Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_search(self, tmp_path: pytest.TempPathFactory) -> None:
        """T_9.5: searching an empty store returns [] without raising."""
        store = LanceDBVectorStore(str(tmp_path))

        sym_results = store.search_symbols(_make_vector("anything"), limit=5)
        file_results = store.search_files(_make_vector("anything"), limit=5)

        assert sym_results == []
        assert file_results == []

        store.close()

    def test_clear(self, tmp_path: pytest.TempPathFactory) -> None:
        """T_9.5: clear() drops all data; subsequent searches return []."""
        store = LanceDBVectorStore(str(tmp_path))

        store.upsert_symbol_embedding(1, 1, "fn", "mod.fn", "function", "f.py", "def fn", _make_vector("fn"))
        store.upsert_file_embedding(1, "f.py", "python", "content", _make_vector("f.py"))

        # Sanity-check: data is present before clear.
        assert len(store.search_symbols(_make_vector("fn"), limit=5)) > 0
        assert len(store.search_files(_make_vector("f.py"), limit=5)) > 0

        store.clear()

        # After clear both tables should be empty.
        assert store.search_symbols(_make_vector("fn"), limit=5) == []
        assert store.search_files(_make_vector("f.py"), limit=5) == []

        store.close()
