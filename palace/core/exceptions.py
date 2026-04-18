"""Exception hierarchy for Code Palace."""

from __future__ import annotations


class PalaceError(Exception):
    """Base exception for all Code Palace errors."""


class ConfigError(PalaceError):
    """Raised when .palace/ is missing or config.json is malformed."""


class StoreError(PalaceError):
    """Raised on DuckDB connection, schema, or query failures."""


class ParseError(PalaceError):
    """Raised on tree-sitter parse failures."""


class EmbeddingError(PalaceError):
    """Raised on ONNX model load or inference failures."""


class LLMError(PalaceError):
    """Raised on LLM API call failures."""


class MCPError(PalaceError):
    """Raised on MCP protocol or transport errors."""
