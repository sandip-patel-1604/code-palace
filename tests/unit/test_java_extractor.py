"""T_3 gate tests — Java extractor validation."""

from __future__ import annotations

from pathlib import Path

from palace.core.models import SymbolKind
from palace.parsing.extractors.java import JavaExtractor


FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "sample_project" / "java_src"


class TestJavaSymbols:
    """T_3.9 — Java symbol extraction for classes, interfaces, enums, methods, fields."""

    def setup_method(self):
        self.extractor = JavaExtractor()

    def test_extracts_public_class(self):
        """T_3.9: Public class declarations are extracted as CLASS with is_exported=True."""
        source = b"public class Foo {}\n"
        result = self.extractor.extract(source, Path("Foo.java"))
        sym = next((s for s in result.symbols if s.name == "Foo"), None)
        assert sym is not None
        assert sym.kind == SymbolKind.CLASS
        assert sym.is_exported is True

    def test_extracts_package_qualified_name(self):
        """T_3.9: Class qualified_name includes the package prefix."""
        source = b"package com.example;\npublic class Bar {}\n"
        result = self.extractor.extract(source, Path("Bar.java"))
        sym = next((s for s in result.symbols if s.name == "Bar"), None)
        assert sym is not None
        assert sym.qualified_name == "com.example.Bar"

    def test_extracts_interface(self):
        """T_3.9: Interface declarations are extracted as INTERFACE."""
        source = b"public interface IFoo { void run(); }\n"
        result = self.extractor.extract(source, Path("IFoo.java"))
        sym = next((s for s in result.symbols if s.name == "IFoo"), None)
        assert sym is not None
        assert sym.kind == SymbolKind.INTERFACE

    def test_extracts_enum(self):
        """T_3.9: Enum declarations are extracted as ENUM."""
        source = b"public enum Status { ACTIVE, INACTIVE }\n"
        result = self.extractor.extract(source, Path("Status.java"))
        sym = next((s for s in result.symbols if s.name == "Status"), None)
        assert sym is not None
        assert sym.kind == SymbolKind.ENUM

    def test_extracts_public_method(self):
        """T_3.9: Public methods inside a class are extracted as METHOD."""
        source = b"public class App {\n    public void run() {}\n}\n"
        result = self.extractor.extract(source, Path("App.java"))
        methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
        assert any(m.name == "run" for m in methods)
        m = next(m for m in methods if m.name == "run")
        assert m.is_exported is True
        assert m.parent_name == "App"

    def test_private_method_not_exported(self):
        """T_3.9: Private methods are extracted but is_exported=False."""
        source = b"public class App {\n    private void secret() {}\n}\n"
        result = self.extractor.extract(source, Path("App.java"))
        methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
        m = next((m for m in methods if m.name == "secret"), None)
        assert m is not None
        assert m.is_exported is False

    def test_extracts_final_field_as_constant(self):
        """T_3.9: Fields with final modifier are extracted as CONSTANT."""
        source = b"public class App {\n    public static final int MAX = 100;\n}\n"
        result = self.extractor.extract(source, Path("App.java"))
        consts = [s for s in result.symbols if s.kind == SymbolKind.CONSTANT]
        assert any(c.name == "MAX" for c in consts)

    def test_extracts_non_final_field_as_variable(self):
        """T_3.9: Non-final fields are extracted as VARIABLE."""
        source = b"public class App {\n    private String name;\n}\n"
        result = self.extractor.extract(source, Path("App.java"))
        variables = [s for s in result.symbols if s.kind == SymbolKind.VARIABLE]
        assert any(v.name == "name" for v in variables)

    def test_line_numbers_one_based(self):
        """T_3.9: Line numbers start at 1."""
        source = b"public class App {\n    public void run() {}\n}\n"
        result = self.extractor.extract(source, Path("App.java"))
        cls = next(s for s in result.symbols if s.name == "App")
        assert cls.line_start == 1

    def test_empty_file_no_errors(self):
        """T_3.9: Empty source returns empty extraction."""
        result = self.extractor.extract(b"", Path("Empty.java"))
        assert result.symbols == []
        assert result.errors == []


class TestJavaImports:
    """T_3.10 — Java import declaration extraction."""

    def setup_method(self):
        self.extractor = JavaExtractor()

    def test_extracts_import(self):
        """T_3.10: Import declarations are captured with module path and imported name."""
        source = b"import java.util.List;\npublic class X {}\n"
        result = self.extractor.extract(source, Path("X.java"))
        imp = next((i for i in result.imports if "List" in i.imported_names), None)
        assert imp is not None
        assert imp.module_path == "java.util"

    def test_fixture_app_java(self):
        """T_3.10: Real fixture App.java has class, methods, and imports."""
        source = (FIXTURE_DIR / "App.java").read_bytes()
        result = self.extractor.extract(source, FIXTURE_DIR / "App.java")
        names = [s.name for s in result.symbols]
        assert "App" in names
        # Check that imports were captured
        assert len(result.imports) >= 1

    def test_fixture_user_service_java(self):
        """T_3.10: Real fixture UserService.java has package-qualified class."""
        source = (FIXTURE_DIR / "service" / "UserService.java").read_bytes()
        result = self.extractor.extract(source, FIXTURE_DIR / "service" / "UserService.java")
        names = [s.name for s in result.symbols]
        assert "UserService" in names
        cls = next(s for s in result.symbols if s.name == "UserService")
        assert cls.qualified_name == "com.example.service.UserService"
