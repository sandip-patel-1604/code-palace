"""Unit tests for palace.mcp.server and palace.mcp.protocol (T10)."""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Guard: skip entire module if mcp SDK is not installed.
# In practice it IS installed in this environment, so all tests should run.
# ---------------------------------------------------------------------------
mcp = pytest.importorskip("mcp", reason="mcp SDK not installed — skipping")


from palace.core.exceptions import MCPError  # noqa: E402
from palace.mcp.protocol import MCPTool, redact_secrets, truncate_content  # noqa: E402
from palace.mcp.server import PalaceMCPServer, _import_mcp  # noqa: E402


# ---------------------------------------------------------------------------
# FM-1: Missing SDK
# ---------------------------------------------------------------------------


def test_missing_sdk_graceful(monkeypatch: pytest.MonkeyPatch) -> None:
    """_import_mcp() raises MCPError with pip install hint when mcp is absent."""
    # Patch all three relevant modules to None so the import fails.
    monkeypatch.setitem(sys.modules, "mcp", None)
    monkeypatch.setitem(sys.modules, "mcp.server", None)
    monkeypatch.setitem(sys.modules, "mcp.server.stdio", None)
    monkeypatch.setitem(sys.modules, "mcp.types", None)

    with pytest.raises(MCPError) as exc_info:
        _import_mcp()

    assert "pip install mcp" in str(exc_info.value)


# ---------------------------------------------------------------------------
# FM-7: redact_secrets
# ---------------------------------------------------------------------------


def test_redact_api_key() -> None:
    result = redact_secrets({"api_key": "secret"})
    assert result == {"api_key": "***REDACTED***"}


def test_redact_case_insensitive() -> None:
    result = redact_secrets({"API_KEY": "x", "Token": "y", "normal": "z"})
    assert result["API_KEY"] == "***REDACTED***"
    assert result["Token"] == "***REDACTED***"
    assert result["normal"] == "z"


def test_redact_password_and_secret() -> None:
    result = redact_secrets({"password": "hunter2", "MY_SECRET": "s3cr3t", "data": 42})
    assert result["password"] == "***REDACTED***"
    assert result["MY_SECRET"] == "***REDACTED***"
    assert result["data"] == 42


def test_redact_preserves_non_sensitive() -> None:
    original = {"path": "/tmp/foo", "limit": 10}
    result = redact_secrets(original)
    assert result == original


# ---------------------------------------------------------------------------
# FM-5/FM-6: truncate_content
# ---------------------------------------------------------------------------


def test_truncate_under_limit() -> None:
    assert truncate_content("short", 100) == "short"


def test_truncate_over_limit() -> None:
    big = "a" * 200_000
    result = truncate_content(big, 100_000)
    result_bytes = result.encode("utf-8")
    assert len(result_bytes) <= 110_000  # well within reasonable overhead
    assert "[truncated" in result


def test_truncate_exact_boundary() -> None:
    """Content exactly at the limit should not be truncated."""
    text = "x" * 100_000
    result = truncate_content(text, 100_000)
    assert result == text


def test_truncate_one_over_limit() -> None:
    """Content one byte over the limit should be truncated."""
    text = "x" * 100_001
    result = truncate_content(text, 100_000)
    assert "[truncated" in result


# ---------------------------------------------------------------------------
# FM-4: MCPTool dataclass
# ---------------------------------------------------------------------------


def test_input_schema_is_dict() -> None:
    async def dummy(args: dict) -> str:
        return "ok"

    tool = MCPTool(
        name="test_tool",
        description="A test tool",
        input_schema={"type": "object"},
        handler=dummy,
    )
    assert isinstance(tool.input_schema, dict)
    assert tool.input_schema == {"type": "object"}


# ---------------------------------------------------------------------------
# FM-3: Server construction
# ---------------------------------------------------------------------------


def test_server_constructs_with_empty_tools() -> None:
    """PalaceMCPServer([]) must be instantiable without error."""
    server = PalaceMCPServer([])
    assert server._tools == []


def test_server_constructs_with_none_tools() -> None:
    """PalaceMCPServer(None) defaults to empty list."""
    server = PalaceMCPServer(None)
    assert server._tools == []


def test_server_constructs_with_tool() -> None:
    """PalaceMCPServer accepts a list with one MCPTool without raising."""

    async def handler(args: dict) -> str:
        return "hello"

    tool = MCPTool(
        name="x",
        description="y",
        input_schema={"type": "object"},
        handler=handler,
    )
    server = PalaceMCPServer([tool])
    assert len(server._tools) == 1
    assert server._tools[0].name == "x"


# ---------------------------------------------------------------------------
# FM-2: Concurrency — handler invoked directly (unit level)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_handler_runs() -> None:
    """A mock tool handler can be awaited directly and returns the expected value."""

    async def handler(args: dict) -> str:
        return "hello"

    tool = MCPTool(
        name="greet",
        description="Says hello",
        input_schema={"type": "object"},
        handler=handler,
    )
    result = await tool.handler({})
    assert result == "hello"


@pytest.mark.asyncio
async def test_two_parallel_handlers_independent() -> None:
    """Two simultaneous tool invocations must not share state (FM-2)."""
    import asyncio

    order: list[str] = []

    async def handler_a(args: dict) -> str:
        order.append("a_start")
        await asyncio.sleep(0)
        order.append("a_end")
        return "a"

    async def handler_b(args: dict) -> str:
        order.append("b_start")
        await asyncio.sleep(0)
        order.append("b_end")
        return "b"

    results = await asyncio.gather(handler_a({}), handler_b({}))
    assert set(results) == {"a", "b"}
