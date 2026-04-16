"""T_3 gate tests — Python extractor validation."""

from __future__ import annotations

from pathlib import Path

from palace.core.models import SymbolKind
from palace.parsing.extractors.python import PythonExtractor


FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "sample_project"


class TestPythonSymbols:
    """T_3.1 — Python symbol extraction correctness."""

    def setup_method(self):
        self.extractor = PythonExtractor()

    def test_extracts_top_level_function(self):
        """T_3.1: Functions at module scope are extracted as FUNCTION kind."""
        source = b"def greet(name: str) -> str:\n    return name\n"
        result = self.extractor.extract(source, Path("test.py"))
        names = [s.name for s in result.symbols]
        assert "greet" in names
        sym = next(s for s in result.symbols if s.name == "greet")
        assert sym.kind == SymbolKind.FUNCTION

    def test_extracts_class(self):
        """T_3.1: Class definitions are extracted as CLASS kind."""
        source = b"class Foo:\n    pass\n"
        result = self.extractor.extract(source, Path("test.py"))
        names = [s.name for s in result.symbols]
        assert "Foo" in names
        sym = next(s for s in result.symbols if s.name == "Foo")
        assert sym.kind == SymbolKind.CLASS

    def test_extracts_method_inside_class(self):
        """T_3.1: Methods inside a class are extracted as METHOD kind with parent_name set."""
        source = b"class Bar:\n    def do_thing(self) -> None:\n        pass\n"
        result = self.extractor.extract(source, Path("test.py"))
        methods = [s for s in result.symbols if s.kind == SymbolKind.METHOD]
        assert len(methods) >= 1
        method = methods[0]
        assert method.name == "do_thing"
        assert method.parent_name == "Bar"

    def test_extracts_module_level_assignment(self):
        """T_3.1: Module-level assignments are extracted as VARIABLE kind."""
        source = b"MY_CONST = 42\n"
        result = self.extractor.extract(source, Path("test.py"))
        vars_ = [s for s in result.symbols if s.kind == SymbolKind.VARIABLE]
        assert any(s.name == "MY_CONST" for s in vars_)

    def test_line_numbers_are_one_based(self):
        """T_3.1: Extracted line numbers start at 1, not 0."""
        source = b"def first():\n    pass\n\ndef second():\n    pass\n"
        result = self.extractor.extract(source, Path("test.py"))
        first = next(s for s in result.symbols if s.name == "first")
        assert first.line_start == 1
        second = next(s for s in result.symbols if s.name == "second")
        assert second.line_start == 4


class TestPythonExportVisibility:
    """T_3.2 — Python export detection via underscore convention."""

    def setup_method(self):
        self.extractor = PythonExtractor()

    def test_public_function_is_exported(self):
        """T_3.2: Functions without leading underscore are marked is_exported=True."""
        source = b"def public_fn():\n    pass\n"
        result = self.extractor.extract(source, Path("test.py"))
        sym = next(s for s in result.symbols if s.name == "public_fn")
        assert sym.is_exported is True

    def test_private_function_not_exported(self):
        """T_3.2: Functions with leading underscore have is_exported=False."""
        source = b"def _private():\n    pass\n"
        result = self.extractor.extract(source, Path("test.py"))
        sym = next(s for s in result.symbols if s.name == "_private")
        assert sym.is_exported is False

    def test_private_variable_not_exported(self):
        """T_3.2: Module-level variables with leading underscore have is_exported=False."""
        source = b"_hidden = 'secret'\n"
        result = self.extractor.extract(source, Path("test.py"))
        sym = next(s for s in result.symbols if s.name == "_hidden")
        assert sym.is_exported is False


class TestPythonDocstrings:
    """T_3.3 — Docstring extraction from functions and classes."""

    def setup_method(self):
        self.extractor = PythonExtractor()

    def test_function_docstring_extracted(self):
        """T_3.3: First string in function body is extracted as docstring."""
        source = b'def foo():\n    """My docstring."""\n    return 1\n'
        result = self.extractor.extract(source, Path("test.py"))
        sym = next(s for s in result.symbols if s.name == "foo")
        assert sym.docstring == "My docstring."

    def test_class_docstring_extracted(self):
        """T_3.3: First string in class body is extracted as docstring."""
        source = b'class Bar:\n    """Bar docstring."""\n    pass\n'
        result = self.extractor.extract(source, Path("test.py"))
        sym = next(s for s in result.symbols if s.name == "Bar")
        assert sym.docstring == "Bar docstring."

    def test_no_docstring_returns_none(self):
        """T_3.3: Functions without a docstring have docstring=None."""
        source = b"def no_doc():\n    return 42\n"
        result = self.extractor.extract(source, Path("test.py"))
        sym = next(s for s in result.symbols if s.name == "no_doc")
        assert sym.docstring is None


class TestPythonImports:
    """T_3.4 — Import extraction covers absolute and relative forms."""

    def setup_method(self):
        self.extractor = PythonExtractor()

    def test_absolute_import(self):
        """T_3.4: Simple absolute import is captured."""
        source = b"import os\n"
        result = self.extractor.extract(source, Path("test.py"))
        modules = [i.module_path for i in result.imports]
        assert "os" in modules

    def test_from_import(self):
        """T_3.4: from-import captures module and imported names."""
        source = b"from pathlib import Path\n"
        result = self.extractor.extract(source, Path("test.py"))
        imp = next(i for i in result.imports if i.module_path == "pathlib")
        assert "Path" in imp.imported_names

    def test_relative_import(self):
        """T_3.4: Relative imports have is_relative=True."""
        source = b"from . import utils\n"
        result = self.extractor.extract(source, Path("test.py"))
        rel = [i for i in result.imports if i.is_relative]
        assert len(rel) >= 1

    def test_relative_import_with_module(self):
        """T_3.4: Relative imports from sub-module capture module path with dot prefix."""
        source = b"from .utils import helper\n"
        result = self.extractor.extract(source, Path("test.py"))
        rel = [i for i in result.imports if i.is_relative]
        assert len(rel) >= 1
        assert any(".utils" in i.module_path or "utils" in i.module_path for i in rel)

    def test_multi_name_from_import(self):
        """T_3.4: from foo import A, B captures both A and B."""
        source = b"from foo import A, B\n"
        result = self.extractor.extract(source, Path("test.py"))
        imp = next(i for i in result.imports if i.module_path == "foo")
        assert "A" in imp.imported_names
        assert "B" in imp.imported_names

    def test_empty_file_no_errors(self):
        """T_3.4: Empty source returns an empty FileExtraction with no errors."""
        result = self.extractor.extract(b"", Path("empty.py"))
        assert result.symbols == []
        assert result.imports == []
        assert result.errors == []

    def test_fixture_app_py(self):
        """T_3.4: Real fixture app.py produces expected symbols and imports."""
        source = (FIXTURE_DIR / "app.py").read_bytes()
        result = self.extractor.extract(source, FIXTURE_DIR / "app.py")
        names = [s.name for s in result.symbols]
        assert "Application" in names
        assert "create_app" in names
        # Relative imports present
        relative = [i for i in result.imports if i.is_relative]
        assert len(relative) >= 1
