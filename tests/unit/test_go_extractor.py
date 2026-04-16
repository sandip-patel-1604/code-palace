"""T_3 gate tests — Go extractor validation."""

from __future__ import annotations

from pathlib import Path

from palace.core.models import SymbolKind
from palace.parsing.extractors.go import GoExtractor


FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "sample_project" / "go_src"


class TestGoSymbols:
    """T_3.7 — Go symbol extraction for functions, methods, types, consts, vars."""

    def setup_method(self):
        self.extractor = GoExtractor()

    def test_extracts_function(self):
        """T_3.7: Function declarations are extracted as FUNCTION."""
        source = b"package main\nfunc Run() int { return 0 }\n"
        result = self.extractor.extract(source, Path("test.go"))
        sym = next((s for s in result.symbols if s.name == "Run"), None)
        assert sym is not None
        assert sym.kind == SymbolKind.FUNCTION

    def test_extracts_method_with_receiver(self):
        """T_3.7: Method declarations have kind METHOD and parent_name set to receiver type."""
        source = b"package main\ntype T struct{}\nfunc (t *T) Foo() string { return \"\" }\n"
        result = self.extractor.extract(source, Path("test.go"))
        method = next((s for s in result.symbols if s.kind == SymbolKind.METHOD), None)
        assert method is not None
        assert method.name == "Foo"
        assert method.parent_name == "T"

    def test_extracts_struct(self):
        """T_3.7: Type specs with struct body are extracted as STRUCT."""
        source = b"package main\ntype User struct { Name string }\n"
        result = self.extractor.extract(source, Path("test.go"))
        sym = next((s for s in result.symbols if s.name == "User"), None)
        assert sym is not None
        assert sym.kind == SymbolKind.STRUCT

    def test_extracts_interface(self):
        """T_3.7: Type specs with interface body are extracted as INTERFACE."""
        source = b"package main\ntype Doer interface { Do() error }\n"
        result = self.extractor.extract(source, Path("test.go"))
        sym = next((s for s in result.symbols if s.name == "Doer"), None)
        assert sym is not None
        assert sym.kind == SymbolKind.INTERFACE

    def test_extracts_const(self):
        """T_3.7: const declarations are extracted as CONSTANT."""
        source = b"package main\nconst MaxSize = 100\n"
        result = self.extractor.extract(source, Path("test.go"))
        sym = next((s for s in result.symbols if s.name == "MaxSize"), None)
        assert sym is not None
        assert sym.kind == SymbolKind.CONSTANT

    def test_extracts_var(self):
        """T_3.7: var declarations are extracted as VARIABLE."""
        source = b"package main\nvar Timeout = 30\n"
        result = self.extractor.extract(source, Path("test.go"))
        sym = next((s for s in result.symbols if s.name == "Timeout"), None)
        assert sym is not None
        assert sym.kind == SymbolKind.VARIABLE

    def test_export_uppercase(self):
        """T_3.7: Identifiers starting with uppercase are is_exported=True."""
        source = b"package main\nfunc Exported() {}\nfunc unexported() {}\n"
        result = self.extractor.extract(source, Path("test.go"))
        exp = next(s for s in result.symbols if s.name == "Exported")
        unexp = next(s for s in result.symbols if s.name == "unexported")
        assert exp.is_exported is True
        assert unexp.is_exported is False

    def test_line_numbers_one_based(self):
        """T_3.7: Line numbers start at 1."""
        source = b"package main\nfunc First() {}\nfunc Second() {}\n"
        result = self.extractor.extract(source, Path("test.go"))
        first = next(s for s in result.symbols if s.name == "First")
        assert first.line_start == 2
        second = next(s for s in result.symbols if s.name == "Second")
        assert second.line_start == 3

    def test_empty_file_no_errors(self):
        """T_3.7: Empty source returns empty extraction with no errors."""
        result = self.extractor.extract(b"", Path("empty.go"))
        assert result.symbols == []
        assert result.errors == []


class TestGoImports:
    """T_3.8 — Go import extraction for single and grouped forms."""

    def setup_method(self):
        self.extractor = GoExtractor()

    def test_single_import(self):
        """T_3.8: Single import statement is captured."""
        source = b'package main\nimport "fmt"\n'
        result = self.extractor.extract(source, Path("test.go"))
        modules = [i.module_path for i in result.imports]
        assert "fmt" in modules

    def test_grouped_import(self):
        """T_3.8: Grouped import block captures all paths."""
        source = b'package main\nimport (\n\t"fmt"\n\t"os"\n)\n'
        result = self.extractor.extract(source, Path("test.go"))
        modules = [i.module_path for i in result.imports]
        assert "fmt" in modules
        assert "os" in modules

    def test_fixture_main_go(self):
        """T_3.8: Real fixture main.go has expected functions and grouped imports."""
        source = (FIXTURE_DIR / "main.go").read_bytes()
        result = self.extractor.extract(source, FIXTURE_DIR / "main.go")
        names = [s.name for s in result.symbols]
        assert "main" in names
        assert "run" in names
        # Grouped imports from fixture
        modules = [i.module_path for i in result.imports]
        assert "fmt" in modules

    def test_fixture_handler_go(self):
        """T_3.8: Real fixture handler.go has struct, interface, method, const, var."""
        source = (FIXTURE_DIR / "handler.go").read_bytes()
        result = self.extractor.extract(source, FIXTURE_DIR / "handler.go")
        kinds = {s.name: s.kind for s in result.symbols}
        assert kinds.get("User") == SymbolKind.STRUCT
        assert kinds.get("Greeter") == SymbolKind.INTERFACE
        assert kinds.get("Greet") == SymbolKind.METHOD
        assert kinds.get("MaxConnections") == SymbolKind.CONSTANT
        assert kinds.get("DefaultTimeout") == SymbolKind.VARIABLE
