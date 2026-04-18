"""Centralized logging setup for Code Palace."""

from __future__ import annotations

import logging
import os
import sys


_ROOT_LOGGER_NAME = "palace"
_DEFAULT_LEVEL = "WARNING"
_configured = False


def get_logger(name: str) -> logging.Logger:
    """Return a logger under the palace hierarchy.

    On first call, configures the root 'palace' logger with either a Rich
    handler (TTY) or plain StreamHandler (non-TTY / piped / MCP server).
    Level is read from the PALACE_LOG_LEVEL env var; defaults to WARNING.
    """
    _ensure_configured()
    return logging.getLogger(name)


def _ensure_configured() -> None:
    """Configure the palace root logger once."""
    global _configured  # noqa: PLW0603
    if _configured:
        return
    _configured = True

    root = logging.getLogger(_ROOT_LOGGER_NAME)

    # Parse level from env var, fall back to WARNING on invalid values
    level_name = os.environ.get("PALACE_LOG_LEVEL", _DEFAULT_LEVEL).upper()
    level = getattr(logging, level_name, None)
    if not isinstance(level, int):
        level = logging.WARNING

    root.setLevel(level)

    # Avoid duplicate handlers on re-import
    if root.handlers:
        return

    # Use Rich handler for TTY, plain StreamHandler otherwise
    if sys.stderr.isatty():
        try:
            from rich.logging import RichHandler

            handler: logging.Handler = RichHandler(
                rich_tracebacks=True,
                show_path=False,
                markup=False,
            )
        except ImportError:
            handler = _plain_handler()
    else:
        handler = _plain_handler()

    handler.setLevel(level)
    root.addHandler(handler)


def _plain_handler() -> logging.StreamHandler:
    """Create a plain stderr handler with a simple format."""
    handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    handler.setFormatter(formatter)
    return handler
