"""T_14.1 — Logging framework tests."""

from __future__ import annotations

import logging
import os

import pytest


class TestGetLogger:
    """T_14.1.1 — get_logger returns a logger under the palace hierarchy."""

    def test_logger_name(self) -> None:
        from palace.core.logging import get_logger

        log = get_logger("palace.core")
        assert log.name == "palace.core"

    def test_logger_hierarchy(self) -> None:
        from palace.core.logging import get_logger

        log = get_logger("palace.graph.builder")
        # Logger must be under the palace root hierarchy
        assert log.name.startswith("palace.")
        # Root palace logger must be an ancestor
        root = logging.getLogger("palace")
        parent = log.parent
        while parent is not None and parent.name != "palace":
            parent = parent.parent
        assert parent is not None
        assert parent.name == "palace"


class TestEnvVarLevel:
    """T_14.1.2 — PALACE_LOG_LEVEL env var controls log level."""

    def setup_method(self) -> None:
        # Reset configured flag so env var is re-read
        import palace.core.logging as mod

        mod._configured = False
        root = logging.getLogger("palace")
        root.handlers.clear()

    def teardown_method(self) -> None:
        os.environ.pop("PALACE_LOG_LEVEL", None)
        import palace.core.logging as mod

        mod._configured = False
        root = logging.getLogger("palace")
        root.handlers.clear()

    def test_debug_level(self) -> None:
        os.environ["PALACE_LOG_LEVEL"] = "DEBUG"
        from palace.core.logging import get_logger

        log = get_logger("palace.test.debug")
        root = logging.getLogger("palace")
        assert root.level == logging.DEBUG

    def test_invalid_level_falls_back(self) -> None:
        os.environ["PALACE_LOG_LEVEL"] = "BOGUS"
        from palace.core.logging import get_logger

        log = get_logger("palace.test.bogus")
        root = logging.getLogger("palace")
        assert root.level == logging.WARNING


class TestNonTTY:
    """T_14.1.4 — Non-TTY context uses plain formatter (no Rich markup)."""

    def setup_method(self) -> None:
        import palace.core.logging as mod

        mod._configured = False
        root = logging.getLogger("palace")
        root.handlers.clear()

    def teardown_method(self) -> None:
        import palace.core.logging as mod

        mod._configured = False
        root = logging.getLogger("palace")
        root.handlers.clear()

    def test_plain_handler_on_non_tty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import sys

        monkeypatch.setattr(sys.stderr, "isatty", lambda: False)

        from palace.core.logging import get_logger

        get_logger("palace.test.nontty")
        root = logging.getLogger("palace")
        assert len(root.handlers) >= 1
        handler = root.handlers[0]
        assert isinstance(handler, logging.StreamHandler)
        # Should NOT be a RichHandler
        assert type(handler).__name__ != "RichHandler"
