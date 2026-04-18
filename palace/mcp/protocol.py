"""MCP protocol helpers: redaction, truncation, and tool dataclass."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

_SECRET_PATTERN = re.compile(r"(?i)(api_key|token|secret|password)")
_REDACTED = "***REDACTED***"


def redact_secrets(args: dict) -> dict:
    """Return a copy of *args* with sensitive values replaced by ``***REDACTED***``.

    Keys matching ``api_key``, ``token``, ``secret``, or ``password``
    (case-insensitive) are redacted.
    """
    result: dict = {}
    for key, value in args.items():
        if _SECRET_PATTERN.search(str(key)):
            result[key] = _REDACTED
        else:
            result[key] = value
    return result


def truncate_content(text: str, max_bytes: int = 100_000) -> str:
    """Truncate *text* to *max_bytes* UTF-8 bytes if necessary.

    If truncation is needed, appends a notice indicating how many bytes were
    omitted.
    """
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    omitted = len(encoded) - max_bytes
    truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return truncated + f"\n\n... [truncated, {omitted} bytes omitted]"


@dataclass
class MCPTool:
    """Descriptor for a single MCP tool registered with :class:`PalaceMCPServer`.

    Attributes:
        name: Unique tool name used in JSON-RPC calls.
        description: Human-readable description shown to the LLM client.
        input_schema: JSON Schema dict describing the tool's parameters.
        handler: Async callable that receives the tool arguments dict and
            returns a result string.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict], Awaitable[str]]
