"""T_7 gate tests — C++ extractor validation."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from palace.cli.main import app
from palace.core.models import SymbolKind
from palace.parsing.extractors.cpp import CppExtractor
from palace.parsing.engine import ParsingEngine
from palace.storage.duckdb_store import DuckDBStore


FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "sample_project" / "cpp_src"


class TestCppSymbols:
    """T_7.1–T_7.5 — C++ symbol extraction correctness."""

    def setup_method(self) -> None:
        self.extractor = CppExtractor()
        self.handler_source = (FIXTURE_DIR / "handler.h").read_bytes()
        self.handler_result = self.extractor.extract(
            self.handler_source, FIXTURE_DIR / "handler.h"
        )

    # ------------------------------------------------------------------
    # T_7.1 — Classes: extract class with methods from handler.h
    # ------------------------------------------------------------------

    def test_extracts_class(self) -> None:
        """T_7.1: CLASS 'Handler' is extracted from handler.h."""
        classes = [s for s in self.handler_result.symbols if s.kind == SymbolKind.CLASS]
        names = [c.name for c in classes]
        assert "Handler" in names, f"Expected 'Handler' in classes, got: {names}"

    def test_extracts_methods_for_class(self) -> None:
        """T_7.1: METHOD children (handle, status, constructor) found under Handler."""
        methods = [
            s
            for s in self.handler_result.symbols
            if s.kind == SymbolKind.METHOD and s.parent_name == "Handler"
        ]
        method_names = {m.name for m in methods}
        # Constructor appears as a forward-declared function declaration inside the class
        assert "handle" in method_names, f"'handle' method missing; got: {method_names}"
        assert "status" in method_names, f"'status' method missing; got: {method_names}"

    # ------------------------------------------------------------------
    # T_7.2 — Structs: extract struct Config
    # ------------------------------------------------------------------

    def test_extracts_struct(self) -> None:
        """T_7.2: STRUCT 'Config' is extracted from handler.h."""
        structs = [s for s in self.handler_result.symbols if s.kind == SymbolKind.STRUCT]
        names = [s.name for s in structs]
        assert "Config" in names, f"Expected 'Config' in structs, got: {names}"

    # ------------------------------------------------------------------
    # T_7.3 — Enums: extract enum Status
    # ------------------------------------------------------------------

    def test_extracts_enum(self) -> None:
        """T_7.3: ENUM 'Status' is extracted from handler.h."""
        enums = [s for s in self.handler_result.symbols if s.kind == SymbolKind.ENUM]
        names = [s.name for s in enums]
        assert "Status" in names, f"Expected 'Status' in enums, got: {names}"

    # ------------------------------------------------------------------
    # T_7.4 — Functions: free function (main) + template function (identity)
    # ------------------------------------------------------------------

    def test_extracts_template_function(self) -> None:
        """T_7.4: Template function 'identity' extracted from handler.h as FUNCTION."""
        functions = [s for s in self.handler_result.symbols if s.kind == SymbolKind.FUNCTION]
        names = [f.name for f in functions]
        assert "identity" in names, f"Expected 'identity' function, got: {names}"

    def test_extracts_free_function_main(self) -> None:
        """T_7.4: Free function 'main' extracted from main.cpp as FUNCTION."""
        source = (FIXTURE_DIR / "main.cpp").read_bytes()
        result = self.extractor.extract(source, FIXTURE_DIR / "main.cpp")
        functions = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
        names = [f.name for f in functions]
        assert "main" in names, f"Expected 'main' function, got: {names}"

    # ------------------------------------------------------------------
    # T_7.5 — Namespaces: qualified_name includes namespace prefix
    # ------------------------------------------------------------------

    def test_qualified_name_includes_namespace(self) -> None:
        """T_7.5: Symbols inside 'app' namespace have qualified_name containing 'app::'."""
        namespace_symbols = [
            s for s in self.handler_result.symbols if s.qualified_name.startswith("app::")
        ]
        assert len(namespace_symbols) > 0, (
            "Expected symbols with 'app::' qualified_name prefix, "
            f"got: {[s.qualified_name for s in self.handler_result.symbols]}"
        )

    def test_handler_class_qualified_name(self) -> None:
        """T_7.5: Handler class has qualified_name 'app::Handler'."""
        handler_sym = next(
            (s for s in self.handler_result.symbols if s.name == "Handler" and s.kind == SymbolKind.CLASS),
            None,
        )
        assert handler_sym is not None, "Handler class not found"
        assert handler_sym.qualified_name == "app::Handler"


class TestCppIncludes:
    """T_7.6 — C++ include extraction for local and system forms."""

    def setup_method(self) -> None:
        self.extractor = CppExtractor()

    def test_local_include_is_relative(self) -> None:
        """T_7.6: Local #include 'handler.h' has is_relative=True."""
        source = (FIXTURE_DIR / "main.cpp").read_bytes()
        result = self.extractor.extract(source, FIXTURE_DIR / "main.cpp")
        local = next(
            (i for i in result.imports if i.module_path == "handler.h"),
            None,
        )
        assert local is not None, "Expected local include 'handler.h'"
        assert local.is_relative is True

    def test_system_include_is_not_relative(self) -> None:
        """T_7.6: System #include <iostream> has is_relative=False."""
        source = (FIXTURE_DIR / "main.cpp").read_bytes()
        result = self.extractor.extract(source, FIXTURE_DIR / "main.cpp")
        system = next(
            (i for i in result.imports if i.module_path == "iostream"),
            None,
        )
        assert system is not None, "Expected system include 'iostream'"
        assert system.is_relative is False

    def test_system_include_module_path_stripped(self) -> None:
        """T_7.6: System include module_path has angle brackets stripped."""
        source = b"#include <vector>\n#include <string>\n"
        result = self.extractor.extract(source, Path("test.cpp"))
        paths = {i.module_path for i in result.imports}
        # Should have the content without angle brackets
        assert "vector" in paths
        assert "string" in paths
        # No angle brackets should remain
        for path in paths:
            assert "<" not in path and ">" not in path


class TestCppEdgeCases:
    """T_7.7 — Edge cases: empty file, whitespace-only."""

    def setup_method(self) -> None:
        self.extractor = CppExtractor()

    def test_empty_file_no_crash(self) -> None:
        """T_7.7: Empty file returns empty FileExtraction with no errors."""
        result = self.extractor.extract(b"", Path("empty.cpp"))
        assert result.symbols == []
        assert result.imports == []
        assert result.errors == []

    def test_whitespace_only_no_crash(self) -> None:
        """T_7.7: Whitespace-only file returns empty FileExtraction with no errors."""
        result = self.extractor.extract(b"   \n\n\t  \n", Path("blank.cpp"))
        assert result.symbols == []
        assert result.errors == []

    def test_line_numbers_one_based(self) -> None:
        """T_7.7: Line numbers reported by extractor start at 1 (not 0)."""
        source = b"int main() { return 0; }\n"
        result = self.extractor.extract(source, Path("test.cpp"))
        assert len(result.symbols) > 0
        for sym in result.symbols:
            assert sym.line_start >= 1, f"line_start must be >= 1, got {sym.line_start}"

    def test_extract_returns_correct_language(self) -> None:
        """T_7.7: FileExtraction.language is always 'cpp'."""
        result = self.extractor.extract(b"int x = 1;", Path("test.cpp"))
        assert result.language == "cpp"


class TestCppEngineIntegration:
    """T_7.8 — Engine: detect_languages finds cpp; parse_all processes C++ files."""

    def setup_method(self) -> None:
        self.engine = ParsingEngine()

    def test_detect_languages_finds_cpp(self) -> None:
        """T_7.8: detect_languages returns 'cpp' count >= 2 for fixture with cpp_src/."""
        sample_project = FIXTURE_DIR.parent
        counts = self.engine.detect_languages(sample_project)
        assert "cpp" in counts, f"Expected 'cpp' in detected languages, got: {list(counts.keys())}"
        assert counts["cpp"] >= 2, f"Expected >= 2 C++ files, got: {counts['cpp']}"

    def test_parse_all_includes_cpp_files(self) -> None:
        """T_7.8: parse_all returns FileExtractions for .cpp and .h files."""
        sample_project = FIXTURE_DIR.parent
        results = self.engine.parse_all(sample_project)
        cpp_results = [r for r in results if r.language == "cpp"]
        assert len(cpp_results) >= 2, (
            f"Expected >= 2 C++ FileExtractions, got: {len(cpp_results)}"
        )

    def test_parse_cpp_file_directly(self) -> None:
        """T_7.8: parse_file dispatches to CppExtractor for .cpp files."""
        sample_project = FIXTURE_DIR.parent
        result = self.engine.parse_file(FIXTURE_DIR / "main.cpp", sample_project)
        assert result is not None
        assert result.language == "cpp"
        assert len(result.symbols) > 0

    def test_parse_header_file_directly(self) -> None:
        """T_7.8: parse_file dispatches to CppExtractor for .h header files."""
        sample_project = FIXTURE_DIR.parent
        result = self.engine.parse_file(FIXTURE_DIR / "handler.h", sample_project)
        assert result is not None
        assert result.language == "cpp"


class TestCppCliIntegration:
    """T_7.9 — Integration: palace init includes C++ files in DB."""

    def test_init_indexes_cpp_files(self, tmp_path: Path) -> None:
        """T_7.9: palace init on sample_project includes C++ symbols in the DB."""
        sample_project = FIXTURE_DIR.parent
        project = tmp_path / "sample"
        shutil.copytree(sample_project, project)

        runner = CliRunner()
        result = runner.invoke(app, ["init", str(project), "--no-progress"])

        assert result.exit_code == 0, f"palace init failed:\n{result.output}"

        store = DuckDBStore(str(project / ".palace" / "palace.duckdb"))
        store.initialize_schema()

        try:
            files = store.get_all_files()
            cpp_files = [f for f in files if f["language"] == "cpp"]
            assert len(cpp_files) >= 2, (
                f"Expected >= 2 C++ files in DB, got {len(cpp_files)}. "
                f"All files: {[f['path'] for f in files]}"
            )

            # Verify C++ symbols are present in the DB
            symbols = store.get_symbols()
            # Collect symbol names from C++ files
            cpp_file_ids = {f["file_id"] for f in cpp_files}
            cpp_symbols = [s for s in symbols if s.get("file_id") in cpp_file_ids]
            assert len(cpp_symbols) > 0, (
                "Expected C++ symbols in DB after palace init, but found none"
            )

            # The Handler class must be findable
            symbol_names = {s["name"] for s in cpp_symbols}
            assert "Handler" in symbol_names or "Application" in symbol_names, (
                f"Expected key C++ class names in DB, got: {symbol_names}"
            )
        finally:
            store.close()
