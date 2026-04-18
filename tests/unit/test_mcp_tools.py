"""Unit tests for palace.mcp.tools (T11)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from palace.core.config import PalaceConfig
from palace.core.palace import Palace
from palace.mcp.tools import TOOLS
from palace.mcp.tools import (
    deps as deps_tool,
    explain as explain_tool,
    impact as impact_tool,
    plan as plan_tool,
    search as search_tool,
    symbols as symbols_tool,
)
from palace.storage.store import EdgeRecord, FileRecord, SymbolRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def indexed_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Build a minimal palace with two files + two symbols + one edge.

    Avoids the tree-sitter parser entirely (which needs network access).
    """
    project = tmp_path / "sample"
    project.mkdir()
    (project / "app.py").write_text("def main():\n    pass\n", encoding="utf-8")
    (project / "util.py").write_text("def helper():\n    pass\n", encoding="utf-8")

    config = PalaceConfig.initialize(
        path=project, languages=["python"], exclude_patterns=None
    )
    palace = Palace(config)
    palace.open()
    assert palace.store is not None
    store = palace.store

    app_id = store.upsert_file(
        FileRecord(
            path=str(project / "app.py"),
            language="python",
            size_bytes=30,
            line_count=2,
            hash="h1",
        )
    )
    util_id = store.upsert_file(
        FileRecord(
            path=str(project / "util.py"),
            language="python",
            size_bytes=30,
            line_count=2,
            hash="h2",
        )
    )
    store.upsert_symbol(
        SymbolRecord(
            file_id=app_id,
            name="main",
            qualified_name="app.main",
            kind="function",
            line_start=1,
            line_end=2,
            col_start=0,
            col_end=0,
            signature="main()",
        )
    )
    store.upsert_symbol(
        SymbolRecord(
            file_id=util_id,
            name="helper",
            qualified_name="util.helper",
            kind="function",
            line_start=1,
            line_end=2,
            col_start=0,
            col_end=0,
            signature="helper()",
        )
    )
    # app.py depends on util.py
    store.upsert_edge(
        EdgeRecord(
            source_file_id=app_id,
            target_file_id=util_id,
            edge_type="IMPORTS",
        )
    )
    palace.close()

    monkeypatch.chdir(project)
    return project


# ---------------------------------------------------------------------------
# FM: Registration — TOOLS list integrity
# ---------------------------------------------------------------------------


def test_tools_registered() -> None:
    names = {t.name for t in TOOLS}
    assert names == {
        "palace_plan",
        "palace_explain",
        "palace_impact",
        "palace_search",
        "palace_deps",
        "palace_symbols",
    }


def test_each_tool_has_input_schema_and_handler() -> None:
    for t in TOOLS:
        assert isinstance(t.input_schema, dict)
        assert t.input_schema.get("type") == "object"
        assert callable(t.handler)


# ---------------------------------------------------------------------------
# FM: Decoupling — tool modules must NOT import typer, rich.console, or CLI
# ---------------------------------------------------------------------------


def test_tool_modules_have_no_cli_imports() -> None:
    """Tool modules must stay CLI-free (no typer, no rich.console, no palace.cli)."""
    forbidden = re.compile(
        r"^\s*(?:from|import)\s+(typer|rich\.console|palace\.cli)\b",
        re.MULTILINE,
    )
    pkg_dir = Path(__file__).parent.parent.parent / "palace" / "mcp" / "tools"
    for path in pkg_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        match = forbidden.search(text)
        assert match is None, f"{path.name} has forbidden import: {match.group(0)!r}"


# ---------------------------------------------------------------------------
# FM: No palace — graceful error string, not an exception
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_no_palace_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = await plan_tool.run({"task": "add caching"})
    assert "No palace found" in result


@pytest.mark.asyncio
async def test_explain_no_palace_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = await explain_tool.run({"target": "app.py"})
    assert "No palace found" in result


@pytest.mark.asyncio
async def test_impact_no_palace_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = await impact_tool.run({"target": "app.py"})
    assert "No palace found" in result


# ---------------------------------------------------------------------------
# FM: Missing required arguments
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_missing_task() -> None:
    result = await plan_tool.run({})
    assert "`task` is required" in result


@pytest.mark.asyncio
async def test_explain_missing_target() -> None:
    result = await explain_tool.run({})
    assert "`target` is required" in result


@pytest.mark.asyncio
async def test_impact_missing_target() -> None:
    result = await impact_tool.run({})
    assert "`target` is required" in result


@pytest.mark.asyncio
async def test_search_missing_query() -> None:
    result = await search_tool.run({})
    assert "`query` is required" in result


@pytest.mark.asyncio
async def test_deps_missing_target() -> None:
    result = await deps_tool.run({})
    assert "`target` is required" in result


@pytest.mark.asyncio
async def test_deps_invalid_direction(indexed_project: Path) -> None:
    result = await deps_tool.run({"target": "app.py", "direction": "sideways"})
    assert "direction" in result


# ---------------------------------------------------------------------------
# FM: Happy path — tools operate on an indexed project
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_happy_path_no_llm(indexed_project: Path) -> None:
    result = await plan_tool.run({"task": "add caching", "no_llm": True})
    assert isinstance(result, str)
    assert "Change Plan" in result or "caching" in result.lower()


@pytest.mark.asyncio
async def test_explain_unknown_target(indexed_project: Path) -> None:
    result = await explain_tool.run(
        {"target": "does_not_exist.py", "no_llm": True}
    )
    assert "not found" in result


@pytest.mark.asyncio
async def test_explain_happy_path_no_llm(indexed_project: Path) -> None:
    result = await explain_tool.run({"target": "app.py", "no_llm": True})
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_impact_happy_path(indexed_project: Path) -> None:
    result = await impact_tool.run({"target": "app.py"})
    assert "Impact Analysis" in result
    assert "Risk" in result


@pytest.mark.asyncio
async def test_impact_unknown_target(indexed_project: Path) -> None:
    result = await impact_tool.run({"target": "nope.py"})
    assert "not found" in result


@pytest.mark.asyncio
async def test_search_happy_path(indexed_project: Path) -> None:
    result = await search_tool.run({"query": "load config", "limit": 5})
    # Either "No results" or a list of results — both valid
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_deps_happy_path(indexed_project: Path) -> None:
    result = await deps_tool.run({"target": "app.py", "direction": "both"})
    assert "Dependencies" in result or "Dependents" in result


@pytest.mark.asyncio
async def test_symbols_happy_path(indexed_project: Path) -> None:
    result = await symbols_tool.run({"limit": 10})
    assert isinstance(result, str)
    assert "Symbols" in result or "No symbols" in result


@pytest.mark.asyncio
async def test_symbols_with_kind_filter(indexed_project: Path) -> None:
    result = await symbols_tool.run({"kind": "function", "limit": 20})
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_symbols_with_file_filter(indexed_project: Path) -> None:
    result = await symbols_tool.run({"file": "app.py", "limit": 20})
    assert isinstance(result, str)
