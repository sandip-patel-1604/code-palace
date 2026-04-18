"""Unit tests for palace.llm.openai (T3)."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

from palace.core.exceptions import LLMError
from palace.llm.base import Message
from palace.llm.openai import OpenAIProvider


def _install_fake_openai(monkeypatch, client_factory=None, rate_limit_error=None):
    fake = types.ModuleType("openai")

    class _RateLimitError(Exception):
        pass

    fake.RateLimitError = rate_limit_error or _RateLimitError
    fake.OpenAI = client_factory or MagicMock

    monkeypatch.setitem(sys.modules, "openai", fake)
    return fake


def _mk_response(content: str | None):
    response = MagicMock()
    choice = MagicMock()
    message = MagicMock()
    message.content = content
    choice.message = message
    response.choices = [choice]
    return response


def test_missing_sdk_available_false(monkeypatch):
    """FM-1: openai not installed → available() is False."""
    monkeypatch.setitem(sys.modules, "openai", None)
    provider = OpenAIProvider(api_key="k")
    assert provider.available() is False


def test_timeout_raises_llm_error(monkeypatch):
    """FM-2: network failure surfaces as LLMError."""
    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("timeout")
    _install_fake_openai(monkeypatch, client_factory=lambda **_: client)

    provider = OpenAIProvider(api_key="k")
    with pytest.raises(LLMError, match="openai call failed"):
        provider.complete([Message("user", "hi")])


def test_429_retries(monkeypatch):
    """FM-3: rate limit retried 3x."""
    class FakeRateLimit(Exception):
        pass

    client = MagicMock()
    client.chat.completions.create.side_effect = FakeRateLimit("429")
    _install_fake_openai(
        monkeypatch, client_factory=lambda **_: client, rate_limit_error=FakeRateLimit
    )
    import palace.llm.openai as mod

    monkeypatch.setattr(mod.time, "sleep", lambda _: None)

    provider = OpenAIProvider(api_key="k")
    with pytest.raises(LLMError, match="rate limit"):
        provider.complete([Message("user", "hi")])
    assert client.chat.completions.create.call_count == 3


def test_empty_messages_raises():
    """FM-4: empty messages list raises before API call."""
    provider = OpenAIProvider(api_key="k")
    with pytest.raises(LLMError, match="no messages"):
        provider.complete([])


def test_null_content_raises(monkeypatch):
    """FM-5: None content raises LLMError."""
    client = MagicMock()
    client.chat.completions.create.return_value = _mk_response(None)
    _install_fake_openai(monkeypatch, client_factory=lambda **_: client)

    provider = OpenAIProvider(api_key="k")
    with pytest.raises(LLMError, match="empty completion"):
        provider.complete([Message("user", "hi")])


def test_single_turn_completes(monkeypatch):
    """Happy path."""
    client = MagicMock()
    client.chat.completions.create.return_value = _mk_response("hello")
    _install_fake_openai(monkeypatch, client_factory=lambda **_: client)

    provider = OpenAIProvider(api_key="k")
    assert provider.complete([Message("user", "hi")]) == "hello"


def test_registered_in_global_registry():
    from palace.llm.base import PROVIDER_REGISTRY

    assert "openai" in PROVIDER_REGISTRY
