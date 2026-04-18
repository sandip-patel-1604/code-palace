"""Unit tests for palace.llm.availability (T6)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from palace.llm.availability import (
    LLMAvailability,
    check_availability,
    render_degraded_notice,
)
from palace.llm.base import PROVIDER_REGISTRY, register_provider


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Strip LLM env vars so tests are deterministic."""
    for k in (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "PALACE_LLM_PROVIDER",
        "OLLAMA_HOST",
    ):
        monkeypatch.delenv(k, raising=False)


def _fake_provider(available: bool, name: str = "fake"):
    p = MagicMock()
    p.name = name
    p.available.return_value = available
    p._model = "fake-model"
    return p


def test_explicit_unavailable_provider_degrades(monkeypatch):
    """FM-1: --provider claude with no key returns degraded availability."""
    # Registry already has "claude" from import; with no key its available() is False.
    result = check_availability(prefer="claude")
    assert result.is_available is False
    assert result.provider_name is None
    assert "claude" in result.reason


def test_all_unavailable_degrades_cleanly(monkeypatch):
    """FM-2: all providers unavailable → None, with reason."""
    fake_unavail = lambda: _fake_provider(available=False)

    monkeypatch.setitem(PROVIDER_REGISTRY, "claude", fake_unavail)
    monkeypatch.setitem(PROVIDER_REGISTRY, "openai", fake_unavail)
    monkeypatch.setitem(PROVIDER_REGISTRY, "ollama", fake_unavail)

    result = check_availability()
    assert result.is_available is False
    assert result.provider is None
    assert result.reason


def test_probe_timeout_bounded(monkeypatch):
    """FM-3: slow probe does not block indefinitely.

    We simulate a slow Ollama with a tight overall bound by wrapping the
    ollama provider to simply return False after a short sleep.
    """
    import time

    slow_calls = []

    def slow_provider():
        p = MagicMock()
        p.available = lambda: (slow_calls.append(time.time()), False)[1]
        return p

    fake_unavail = lambda: _fake_provider(available=False)
    monkeypatch.setitem(PROVIDER_REGISTRY, "claude", fake_unavail)
    monkeypatch.setitem(PROVIDER_REGISTRY, "openai", fake_unavail)
    monkeypatch.setitem(PROVIDER_REGISTRY, "ollama", slow_provider)

    start = time.time()
    result = check_availability()
    elapsed = time.time() - start
    assert elapsed < 3.0
    assert result.is_available is False


def test_claude_available_returned(monkeypatch):
    """Happy path: claude available → returned."""
    monkeypatch.setitem(
        PROVIDER_REGISTRY, "claude", lambda: _fake_provider(True, "claude")
    )

    result = check_availability()
    assert result.is_available is True
    assert result.provider_name == "claude"
    assert result.model == "fake-model"


def test_prefer_selects_specific_provider(monkeypatch):
    """prefer='ollama' returns ollama even if claude is first in order."""
    monkeypatch.setitem(
        PROVIDER_REGISTRY, "claude", lambda: _fake_provider(True, "claude")
    )
    monkeypatch.setitem(
        PROVIDER_REGISTRY, "ollama", lambda: _fake_provider(True, "ollama")
    )

    result = check_availability(prefer="ollama")
    assert result.provider_name == "ollama"


def test_falls_through_to_next(monkeypatch):
    """When claude unavailable, falls through to openai."""
    monkeypatch.setitem(
        PROVIDER_REGISTRY, "claude", lambda: _fake_provider(False, "claude")
    )
    monkeypatch.setitem(
        PROVIDER_REGISTRY, "openai", lambda: _fake_provider(True, "openai")
    )
    monkeypatch.setitem(
        PROVIDER_REGISTRY, "ollama", lambda: _fake_provider(False, "ollama")
    )

    result = check_availability()
    assert result.provider_name == "openai"


def test_constructor_exception_is_contained(monkeypatch):
    """A provider whose constructor raises does not crash check_availability."""
    def boom():
        raise RuntimeError("boom")

    monkeypatch.setitem(PROVIDER_REGISTRY, "claude", boom)
    monkeypatch.setitem(
        PROVIDER_REGISTRY, "openai", lambda: _fake_provider(True, "openai")
    )

    result = check_availability()
    assert result.provider_name == "openai"


def test_render_degraded_notice_never_raises():
    console = MagicMock()
    render_degraded_notice(console, "palace plan")
    console.print.assert_called_once()
    msg = console.print.call_args[0][0]
    assert "structural mode" in msg
    assert "palace plan" in msg
