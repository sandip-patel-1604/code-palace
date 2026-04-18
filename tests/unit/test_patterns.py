"""Unit tests for palace/graph/patterns.py — T5 gate tests."""

from __future__ import annotations

from palace.graph.patterns import CrossCuttingConcern, NamingConvention, PatternDetector
from palace.storage.duckdb_store import DuckDBStore
from palace.storage.store import EdgeRecord, FileRecord, SymbolRecord


# ---------------------------------------------------------------------------
# Helpers to seed an in-memory store
# ---------------------------------------------------------------------------


def _make_store() -> DuckDBStore:
    store = DuckDBStore(":memory:")
    store.initialize_schema()
    return store


def _add_file(store: DuckDBStore, path: str) -> int:
    return store.upsert_file(FileRecord(
        path=path,
        language="python",
        size_bytes=100,
        line_count=10,
        hash="abc",
    ))


def _add_symbol(
    store: DuckDBStore,
    file_id: int,
    name: str,
    kind: str = "function",
) -> int:
    return store.upsert_symbol(SymbolRecord(
        file_id=file_id,
        name=name,
        qualified_name=name,
        kind=kind,
        line_start=1,
        line_end=5,
        col_start=0,
        col_end=0,
    ))


def _add_calls_edge(
    store: DuckDBStore,
    source_file_id: int,
    target_file_id: int,
    source_symbol_id: int | None = None,
    target_symbol_id: int | None = None,
) -> None:
    store.upsert_edge(EdgeRecord(
        source_file_id=source_file_id,
        target_file_id=target_file_id,
        source_symbol_id=source_symbol_id,
        target_symbol_id=target_symbol_id,
        edge_type="CALLS",
    ))


# ---------------------------------------------------------------------------
# T5 tests
# ---------------------------------------------------------------------------


class TestEmptyStore:
    def test_empty_store_returns_empty(self) -> None:
        """FM-2: freshly constructed in-memory DuckDBStore → detect_cross_cutting() == []."""
        store = _make_store()
        detector = PatternDetector(store)
        result = detector.detect_cross_cutting()
        assert result == []


class TestSingleQueryPattern:
    def test_single_query_pattern(self) -> None:
        """FM-3: get_symbols and get_edges each called <= 1 time per detect_cross_cutting()."""
        store = _make_store()

        get_symbols_count = 0
        get_edges_count = 0

        original_get_symbols = store.get_symbols
        original_get_edges = store.get_edges

        def counting_get_symbols(*args, **kwargs):
            nonlocal get_symbols_count
            get_symbols_count += 1
            return original_get_symbols(*args, **kwargs)

        def counting_get_edges(*args, **kwargs):
            nonlocal get_edges_count
            get_edges_count += 1
            return original_get_edges(*args, **kwargs)

        store.get_symbols = counting_get_symbols  # type: ignore[method-assign]
        store.get_edges = counting_get_edges  # type: ignore[method-assign]

        detector = PatternDetector(store)
        detector.detect_cross_cutting()

        assert get_symbols_count <= 1, f"get_symbols called {get_symbols_count} times, expected <= 1"
        assert get_edges_count <= 1, f"get_edges called {get_edges_count} times, expected <= 1"


class TestLocalOnlyLoggerIgnored:
    def test_local_only_logger_ignored(self) -> None:
        """FM-1: log symbol called from files in ONE directory → detect_cross_cutting() returns empty."""
        store = _make_store()

        # Files in one directory: utils/
        fid_log = _add_file(store, "utils/logger.py")
        fid_a = _add_file(store, "utils/helper_a.py")
        fid_b = _add_file(store, "utils/helper_b.py")

        sym_log = _add_symbol(store, fid_log, "log")

        # Both callers are in the same directory
        _add_calls_edge(store, fid_a, fid_log, target_symbol_id=sym_log)
        _add_calls_edge(store, fid_b, fid_log, target_symbol_id=sym_log)

        detector = PatternDetector(store)
        result = detector.detect_cross_cutting()
        assert result == [], f"Expected empty but got: {result}"


class TestDetectsLoggingAcrossThreeDirs:
    def test_detects_logging_across_three_dirs(self) -> None:
        """FM-1 positive: log.info calls from auth/, pipeline/, api/ → returns CrossCuttingConcern(kind='logging')."""
        store = _make_store()

        # Logging module
        fid_log = _add_file(store, "logging_module/log.py")
        sym_log = _add_symbol(store, fid_log, "log")

        # Callers in three different directories
        fid_auth = _add_file(store, "auth/login.py")
        fid_pipe = _add_file(store, "pipeline/runner.py")
        fid_api = _add_file(store, "api/handler.py")

        _add_calls_edge(store, fid_auth, fid_log, target_symbol_id=sym_log)
        _add_calls_edge(store, fid_pipe, fid_log, target_symbol_id=sym_log)
        _add_calls_edge(store, fid_api, fid_log, target_symbol_id=sym_log)

        detector = PatternDetector(store)
        result = detector.detect_cross_cutting()

        logging_concerns = [c for c in result if c.kind == "logging"]
        assert len(logging_concerns) >= 1, f"Expected logging concern, got: {result}"
        concern = logging_concerns[0]
        assert concern.call_site_count >= 3


class TestNamingConventionStillReturned:
    def test_naming_convention_still_returned(self) -> None:
        """Seed store with auth/*_handler.py files → NamingConvention with '_handler' suffix."""
        store = _make_store()

        # Build all_files list as dicts (as returned by store.get_all_files)
        all_files = [
            {"path": "auth/login_handler.py", "language": "python"},
            {"path": "auth/signup_handler.py", "language": "python"},
            {"path": "auth/logout_handler.py", "language": "python"},
        ]

        # matched_files: objects with .path attribute — use simple namespace
        class MockMatchedFile:
            def __init__(self, path: str) -> None:
                self.path = path

        matched_files = [MockMatchedFile("auth/login_handler.py")]

        detector = PatternDetector(store)
        conventions = detector.detect_naming_conventions(all_files, matched_files)

        assert len(conventions) >= 1, f"Expected at least one convention, got: {conventions}"
        # Check that one of the conventions references _handler suffix
        found = any("handler" in c.name.lower() for c in conventions)
        assert found, f"Expected handler pattern in conventions: {[c.name for c in conventions]}"

        # Examples should include the handler files
        all_examples = [ex for c in conventions for ex in c.examples]
        assert any("handler" in ex for ex in all_examples), (
            f"Expected handler examples, got: {all_examples}"
        )


class TestUnicodeSymbolNamesSafe:
    def test_unicode_symbol_names_safe(self) -> None:
        """FM-5: symbol named with unicode (e.g. 日本_logger) must not crash detect_cross_cutting()."""
        store = _make_store()

        # Add files in 3 dirs so we can trigger the threshold check
        fid_log = _add_file(store, "logs/log_module.py")
        sym = _add_symbol(store, fid_log, "日本_logger")

        fid_a = _add_file(store, "auth/a.py")
        fid_b = _add_file(store, "pipeline/b.py")
        fid_c = _add_file(store, "api/c.py")

        _add_calls_edge(store, fid_a, fid_log, target_symbol_id=sym)
        _add_calls_edge(store, fid_b, fid_log, target_symbol_id=sym)
        _add_calls_edge(store, fid_c, fid_log, target_symbol_id=sym)

        detector = PatternDetector(store)
        # Must not raise
        result = detector.detect_cross_cutting()
        assert isinstance(result, list)
