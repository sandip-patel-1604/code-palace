"""T_3 gate tests — ParsingEngine integration validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from palace.parsing.engine import ParsingEngine
from palace.parsing.extractors.base import FileExtraction


FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "sample_project"


class TestParsingEngineDetectLanguages:
    """T_3.11 — ParsingEngine.detect_languages scans extensions correctly."""

    def setup_method(self):
        self.engine = ParsingEngine()

    def test_detect_languages_returns_dict(self):
        """T_3.11: detect_languages returns a dict mapping language to file count."""
        counts = self.engine.detect_languages(FIXTURE_DIR)
        assert isinstance(counts, dict)

    def test_detects_python(self):
        """T_3.11: Python files in fixture dir are counted."""
        counts = self.engine.detect_languages(FIXTURE_DIR)
        assert counts.get("python", 0) >= 4

    def test_detects_typescript(self):
        """T_3.11: TypeScript files in fixture ts_src/ are counted."""
        counts = self.engine.detect_languages(FIXTURE_DIR)
        assert counts.get("typescript", 0) >= 3

    def test_detects_go(self):
        """T_3.11: Go files in fixture go_src/ are counted."""
        counts = self.engine.detect_languages(FIXTURE_DIR)
        assert counts.get("go", 0) >= 2

    def test_detects_java(self):
        """T_3.11: Java files in fixture java_src/ are counted."""
        counts = self.engine.detect_languages(FIXTURE_DIR)
        assert counts.get("java", 0) >= 2


class TestParsingEngineParseFile:
    """T_3.11 — ParsingEngine.parse_file dispatches to correct extractor."""

    def setup_method(self):
        self.engine = ParsingEngine()

    def test_parse_python_file(self):
        """T_3.11: Parsing a .py fixture returns FileExtraction with language=python."""
        extraction = self.engine.parse_file(FIXTURE_DIR / "app.py", FIXTURE_DIR)
        assert extraction is not None
        assert extraction.language == "python"
        assert len(extraction.symbols) > 0

    def test_parse_typescript_file(self):
        """T_3.11: Parsing a .ts fixture returns FileExtraction with language=typescript."""
        extraction = self.engine.parse_file(
            FIXTURE_DIR / "ts_src" / "types.ts", FIXTURE_DIR
        )
        assert extraction is not None
        assert extraction.language == "typescript"

    def test_parse_go_file(self):
        """T_3.11: Parsing a .go fixture returns FileExtraction with language=go."""
        extraction = self.engine.parse_file(
            FIXTURE_DIR / "go_src" / "handler.go", FIXTURE_DIR
        )
        assert extraction is not None
        assert extraction.language == "go"

    def test_parse_java_file(self):
        """T_3.11: Parsing a .java fixture returns FileExtraction with language=java."""
        extraction = self.engine.parse_file(
            FIXTURE_DIR / "java_src" / "App.java", FIXTURE_DIR
        )
        assert extraction is not None
        assert extraction.language == "java"

    def test_parse_unknown_extension_returns_none(self):
        """T_3.11: Files with unknown extension return None."""
        result = self.engine.parse_file(Path("foo.xyz"), FIXTURE_DIR)
        assert result is None

    def test_parse_empty_file(self, tmp_path):
        """T_3.11: An empty .py file returns an empty FileExtraction, not None."""
        empty = tmp_path / "empty.py"
        empty.write_bytes(b"")
        result = self.engine.parse_file(empty, tmp_path)
        assert result is not None
        assert result.symbols == []


class TestParsingEngineParseAll:
    """T_3.12 — ParsingEngine.parse_all discovers and parses all supported files."""

    def setup_method(self):
        self.engine = ParsingEngine()

    def test_parse_all_returns_list(self):
        """T_3.12: parse_all returns a list of FileExtraction objects."""
        results = self.engine.parse_all(FIXTURE_DIR)
        assert isinstance(results, list)
        assert all(isinstance(r, FileExtraction) for r in results)

    def test_parse_all_covers_all_languages(self):
        """T_3.12: parse_all covers Python, TypeScript, Go and Java fixtures."""
        results = self.engine.parse_all(FIXTURE_DIR)
        langs = {r.language for r in results}
        assert "python" in langs
        assert "typescript" in langs
        assert "go" in langs
        assert "java" in langs

    def test_parse_all_excludes_patterns(self, tmp_path):
        """T_3.12: Files in excluded directories are skipped."""
        excluded_dir = tmp_path / "node_modules"
        excluded_dir.mkdir()
        (excluded_dir / "index.ts").write_text("export const x = 1;")
        (tmp_path / "main.py").write_text("def hello(): pass\n")

        results = self.engine.parse_all(tmp_path, exclude=["node_modules"])
        paths = [r.path for r in results]
        assert not any("node_modules" in str(p) for p in paths)
        assert any("main.py" in str(p) for p in paths)

    def test_parse_all_skips_large_file(self, tmp_path):
        """T_3.12: Files larger than 1 MB are skipped."""
        big_file = tmp_path / "huge.py"
        big_file.write_bytes(b"x = 1\n" * 200_000)  # ~1.2 MB
        results = self.engine.parse_all(tmp_path)
        paths = [r.path for r in results]
        assert big_file not in paths

    def test_parse_all_skips_binary_file(self, tmp_path):
        """T_3.12: Files that appear binary are skipped."""
        binary_file = tmp_path / "data.py"
        binary_file.write_bytes(bytes(range(256)) * 40)  # contains many null bytes
        results = self.engine.parse_all(tmp_path)
        paths = [r.path for r in results]
        assert binary_file not in paths

    def test_fixture_total_file_count(self):
        """T_3.12: Fixture sample_project has at least 11 parseable files."""
        results = self.engine.parse_all(FIXTURE_DIR)
        assert len(results) >= 11
