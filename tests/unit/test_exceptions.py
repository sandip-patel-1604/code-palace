"""T_14.2 — Exception hierarchy tests."""

from __future__ import annotations

from palace.core.exceptions import (
    ConfigError,
    EmbeddingError,
    LLMError,
    MCPError,
    PalaceError,
    ParseError,
    StoreError,
)


class TestExceptionHierarchy:
    """T_14.2.1 — All subtypes are subclasses of PalaceError and Exception."""

    def test_palace_error_is_exception(self) -> None:
        assert issubclass(PalaceError, Exception)

    def test_all_subtypes(self) -> None:
        subtypes = [ConfigError, StoreError, ParseError, EmbeddingError, LLMError, MCPError]
        for cls in subtypes:
            assert issubclass(cls, PalaceError), f"{cls.__name__} is not a PalaceError"
            assert issubclass(cls, Exception), f"{cls.__name__} is not an Exception"


class TestMessagePreservation:
    """T_14.2.2 — Exception messages are preserved."""

    def test_store_error_message(self) -> None:
        err = StoreError("database connection failed")
        assert str(err) == "database connection failed"

    def test_config_error_message(self) -> None:
        err = ConfigError("no .palace/ found")
        assert str(err) == "no .palace/ found"


class TestCatchAll:
    """T_14.2.3 — except PalaceError catches all subtypes."""

    def test_catch_all_subtypes(self) -> None:
        subtypes = [ConfigError, StoreError, ParseError, EmbeddingError, LLMError, MCPError]
        for cls in subtypes:
            try:
                raise cls(f"test {cls.__name__}")
            except PalaceError:
                pass  # expected — caught by base class
            else:
                assert False, f"{cls.__name__} not caught by PalaceError"
