"""T_1 gate tests — Project Skeleton validation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


class TestCLI:
    """T_1.2 + T_1.3 — CLI help and version."""

    def test_help_shows_all_commands(self):
        """T_1.2: palace --help shows all 4 commands."""
        result = subprocess.run(
            [sys.executable, "-m", "palace.cli.main", "--help"],
            capture_output=True,
            text=True,
        )
        # Typer doesn't support `python -m` directly, use the app via runner
        from typer.testing import CliRunner
        from palace.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        for cmd in ["init", "symbols", "deps", "plan"]:
            assert cmd in result.output, f"Command '{cmd}' not found in help output"

    def test_version_output(self):
        """T_1.3: palace --version prints correct version."""
        from typer.testing import CliRunner
        from palace.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output


class TestConfig:
    """T_1.4 + T_1.5 — PalaceConfig initialization and discovery."""

    def test_initialize_creates_palace_dir(self, tmp_path: Path):
        """T_1.4: PalaceConfig.initialize() creates .palace/ and config.json."""
        from palace.core.config import PalaceConfig

        config = PalaceConfig.initialize(path=tmp_path)

        assert config.palace_dir.is_dir()
        assert config.db_path.name == "palace.duckdb"

        config_file = config.palace_dir / "config.json"
        assert config_file.exists()

        data = json.loads(config_file.read_text())
        assert "languages" in data
        assert "exclude_patterns" in data

    def test_initialize_roundtrips(self, tmp_path: Path):
        """T_1.4: Config data roundtrips through save/discover."""
        from palace.core.config import PalaceConfig

        original = PalaceConfig.initialize(
            path=tmp_path,
            languages=["python", "typescript"],
            exclude_patterns=["node_modules", ".git"],
        )

        discovered = PalaceConfig.discover(path=tmp_path)
        assert discovered is not None
        assert discovered.root == original.root
        assert discovered.languages == ["python", "typescript"]
        assert discovered.exclude_patterns == ["node_modules", ".git"]

    def test_discover_walks_up(self, tmp_path: Path):
        """T_1.5: discover() finds .palace/ walking up from nested dir."""
        from palace.core.config import PalaceConfig

        PalaceConfig.initialize(path=tmp_path)

        nested = tmp_path / "src" / "deep" / "nested"
        nested.mkdir(parents=True)

        config = PalaceConfig.discover(path=nested)
        assert config is not None
        assert config.root == tmp_path

    def test_discover_returns_none_when_missing(self, tmp_path: Path):
        """T_1.5: discover() returns None when no .palace/ exists."""
        from palace.core.config import PalaceConfig

        config = PalaceConfig.discover(path=tmp_path)
        assert config is None


class TestModels:
    """T_1.6 — SymbolKind and EdgeType enums."""

    def test_symbol_kind_members(self):
        """T_1.6: SymbolKind has all expected members."""
        from palace.core.models import SymbolKind

        expected = {
            "function", "method", "class", "interface", "type_alias",
            "enum", "struct", "variable", "constant", "property",
            "decorator", "module",
        }
        actual = {member.value for member in SymbolKind}
        assert actual == expected

    def test_edge_type_members(self):
        """T_1.6: EdgeType has all expected members."""
        from palace.core.models import EdgeType

        expected = {
            "imports", "calls", "inherits", "implements", "contains",
            "nests", "references", "exports", "type_ref",
        }
        actual = {member.value for member in EdgeType}
        assert actual == expected

    def test_symbol_kind_is_str(self):
        """SymbolKind values are strings (StrEnum)."""
        from palace.core.models import SymbolKind

        assert isinstance(SymbolKind.FUNCTION, str)
        assert SymbolKind.FUNCTION == "function"

    def test_extension_to_language_mapping(self):
        """EXTENSION_TO_LANGUAGE maps common extensions correctly."""
        from palace.core.models import EXTENSION_TO_LANGUAGE

        assert EXTENSION_TO_LANGUAGE[".py"] == "python"
        assert EXTENSION_TO_LANGUAGE[".ts"] == "typescript"
        assert EXTENSION_TO_LANGUAGE[".go"] == "go"
        assert EXTENSION_TO_LANGUAGE[".java"] == "java"
