"""T_3 gate tests — TypeScript extractor validation."""

from __future__ import annotations

from pathlib import Path

from palace.core.models import SymbolKind
from palace.parsing.extractors.typescript import TypeScriptExtractor


FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "sample_project" / "ts_src"


class TestTypeScriptSymbols:
    """T_3.5 — TypeScript symbol extraction for all declaration types."""

    def setup_method(self):
        self.extractor = TypeScriptExtractor()

    def test_extracts_exported_class(self):
        """T_3.5: Exported class declarations are extracted as CLASS with is_exported=True."""
        source = b"export class Foo {}\n"
        result = self.extractor.extract(source, Path("test.ts"))
        sym = next((s for s in result.symbols if s.name == "Foo"), None)
        assert sym is not None
        assert sym.kind == SymbolKind.CLASS
        assert sym.is_exported is True

    def test_non_exported_class_not_exported(self):
        """T_3.5: Class without export keyword has is_exported=False."""
        source = b"class Hidden {}\n"
        result = self.extractor.extract(source, Path("test.ts"))
        sym = next((s for s in result.symbols if s.name == "Hidden"), None)
        assert sym is not None
        assert sym.is_exported is False

    def test_extracts_function_declaration(self):
        """T_3.5: export function declarations are extracted as FUNCTION."""
        source = b"export function hello(x: string): void {}\n"
        result = self.extractor.extract(source, Path("test.ts"))
        sym = next((s for s in result.symbols if s.name == "hello"), None)
        assert sym is not None
        assert sym.kind == SymbolKind.FUNCTION
        assert sym.is_exported is True

    def test_extracts_interface(self):
        """T_3.5: export interface declarations are extracted as INTERFACE."""
        source = b"export interface IFoo { id: number; }\n"
        result = self.extractor.extract(source, Path("test.ts"))
        sym = next((s for s in result.symbols if s.name == "IFoo"), None)
        assert sym is not None
        assert sym.kind == SymbolKind.INTERFACE

    def test_extracts_type_alias(self):
        """T_3.5: export type alias declarations are extracted as TYPE_ALIAS."""
        source = b"export type UserId = number;\n"
        result = self.extractor.extract(source, Path("test.ts"))
        sym = next((s for s in result.symbols if s.name == "UserId"), None)
        assert sym is not None
        assert sym.kind == SymbolKind.TYPE_ALIAS

    def test_extracts_enum(self):
        """T_3.5: export enum declarations are extracted as ENUM."""
        source = b"export enum Status { Active, Inactive }\n"
        result = self.extractor.extract(source, Path("test.ts"))
        sym = next((s for s in result.symbols if s.name == "Status"), None)
        assert sym is not None
        assert sym.kind == SymbolKind.ENUM

    def test_extracts_arrow_function(self):
        """T_3.5: Exported const arrow functions are extracted as FUNCTION."""
        source = b"export const compute = (x: number): number => x * 2;\n"
        result = self.extractor.extract(source, Path("test.ts"))
        sym = next((s for s in result.symbols if s.name == "compute"), None)
        assert sym is not None
        assert sym.kind == SymbolKind.FUNCTION
        assert sym.is_exported is True

    def test_extracts_methods_from_class(self):
        """T_3.5: Methods inside a class body are extracted as METHOD with parent_name."""
        source = b"export class Bar {\n  doThing(x: number): void {}\n}\n"
        result = self.extractor.extract(source, Path("test.ts"))
        methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
        assert len(methods) >= 1
        assert methods[0].parent_name == "Bar"

    def test_line_numbers_one_based(self):
        """T_3.5: Line numbers are 1-based."""
        source = b"export class First {}\n\nexport class Second {}\n"
        result = self.extractor.extract(source, Path("test.ts"))
        first = next(s for s in result.symbols if s.name == "First")
        assert first.line_start == 1
        second = next(s for s in result.symbols if s.name == "Second")
        assert second.line_start == 3

    def test_empty_file_no_errors(self):
        """T_3.5: Empty source produces no symbols and no errors."""
        result = self.extractor.extract(b"", Path("empty.ts"))
        assert result.symbols == []
        assert result.errors == []


class TestTypeScriptImports:
    """T_3.6 — TypeScript ES module import extraction."""

    def setup_method(self):
        self.extractor = TypeScriptExtractor()

    def test_named_imports(self):
        """T_3.6: Named imports { A, B } from '...' are captured."""
        source = b"import { readFile, writeFile } from 'fs';\n"
        result = self.extractor.extract(source, Path("test.ts"))
        imp = next((i for i in result.imports if i.module_path == "fs"), None)
        assert imp is not None
        assert "readFile" in imp.imported_names
        assert "writeFile" in imp.imported_names

    def test_default_import(self):
        """T_3.6: Default import captured as an imported name."""
        source = b"import Default from './default';\n"
        result = self.extractor.extract(source, Path("test.ts"))
        imp = next((i for i in result.imports if "./default" in i.module_path), None)
        assert imp is not None
        assert "Default" in imp.imported_names

    def test_fixture_index_ts(self):
        """T_3.6: Real fixture index.ts has class, function and arrow function extracted."""
        source = (FIXTURE_DIR / "index.ts").read_bytes()
        result = self.extractor.extract(source, FIXTURE_DIR / "index.ts")
        names = [s.name for s in result.symbols]
        assert "UserController" in names
        assert "bootstrapApp" in names
        assert "formatUser" in names

    def test_fixture_types_ts(self):
        """T_3.6: Real fixture types.ts has interface, type aliases and enum."""
        source = (FIXTURE_DIR / "types.ts").read_bytes()
        result = self.extractor.extract(source, FIXTURE_DIR / "types.ts")
        kinds = {s.name: s.kind for s in result.symbols}
        assert kinds.get("IUser") == SymbolKind.INTERFACE
        assert kinds.get("UserId") == SymbolKind.TYPE_ALIAS
        assert kinds.get("UserRole") == SymbolKind.ENUM
