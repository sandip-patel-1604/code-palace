"""Unit tests for palace.llm.anthropic (T2)."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

from palace.core.exceptions import LLMError
from palace.llm.anthropic import AnthropicProvider
from palace.llm.base import Message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _install_fake_anthropic(
    monkeypatch, client_factory=None, rate_limit_error=None, timeout_error=None
):
    """Install a synthetic ``anthropic`` module in sys.modules."""
    fake = types.ModuleType("anthropic")

    class _RateLimitError(Exception):
        pass

    class _APIError(Exception):
        pass

    fake.RateLimitError = rate_limit_error or _RateLimitError
    fake.APIError = _APIError
    fake.APIConnectionError = _APIError
    fake.APITimeoutError = timeout_error or _APIError

    fake.Anthropic = client_factory or MagicMock

    monkeypatch.setitem(sys.modules, "anthropic", fake)
    return fake


def _mk_response(text_blocks: list[str]):
    """Build a fake Anthropic response with the given text blocks."""
    response = MagicMock()
    blocks = []
    for t in text_blocks:
        b = MagicMock()
        b.type = "text"
        b.text = t
        blocks.append(b)
    response.content = blocks
    return response


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_missing_sdk_available_false(monkeypatch):
    """FM-1: `anthropic` not installed → available() is False."""
    monkeypatch.setitem(sys.modules, "anthropic", None)
    provider = AnthropicProvider(api_key="test-key")
    assert provider.available() is False


def test_missing_sdk_complete_raises(monkeypatch):
    """FM-1: `complete()` raises LLMError with install hint."""
    monkeypatch.setitem(sys.modules, "anthropic", None)
    provider = AnthropicProvider(api_key="test-key")
    with pytest.raises(LLMError, match="pip install"):
        provider.complete([Message("user", "hi")])


def test_timeout_raises_llm_error(monkeypatch):
    """FM-2: network timeout surfaces as LLMError."""
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("timeout")
    _install_fake_anthropic(monkeypatch, client_factory=lambda **_: client)

    provider = AnthropicProvider(api_key="k")
    with pytest.raises(LLMError, match="anthropic call failed"):
        provider.complete([Message("user", "hi")])


def test_429_retries_then_fails(monkeypatch):
    """FM-3: rate-limit errors retried 3x before giving up."""
    class FakeRateLimit(Exception):
        pass

    client = MagicMock()
    client.messages.create.side_effect = FakeRateLimit("429")
    _install_fake_anthropic(
        monkeypatch, client_factory=lambda **_: client, rate_limit_error=FakeRateLimit
    )
    # Speed up: patch sleep to no-op.
    import palace.llm.anthropic as mod

    monkeypatch.setattr(mod.time, "sleep", lambda _: None)

    provider = AnthropicProvider(api_key="k")
    with pytest.raises(LLMError, match="rate limit"):
        provider.complete([Message("user", "hi")])
    assert client.messages.create.call_count == 3


def test_system_message_extracted(monkeypatch):
    """FM-4: system messages go into the `system=` kwarg."""
    client = MagicMock()
    client.messages.create.return_value = _mk_response(["ok"])
    _install_fake_anthropic(monkeypatch, client_factory=lambda **_: client)

    provider = AnthropicProvider(api_key="k")
    provider.complete([Message("system", "S"), Message("user", "U")])

    _, kwargs = client.messages.create.call_args
    assert kwargs["system"] == "S"
    assert kwargs["messages"] == [{"role": "user", "content": "U"}]


def test_empty_messages_raises():
    """FM-5: empty messages list raises before any API call."""
    provider = AnthropicProvider(api_key="k")
    with pytest.raises(LLMError, match="no messages"):
        provider.complete([])


def test_multi_block_response_concatenated(monkeypatch):
    """FM-6: multiple text blocks are concatenated in order."""
    client = MagicMock()
    client.messages.create.return_value = _mk_response(["block1", "block2"])
    _install_fake_anthropic(monkeypatch, client_factory=lambda **_: client)

    provider = AnthropicProvider(api_key="k")
    result = provider.complete([Message("user", "hi")])
    assert result == "block1block2"


def test_single_turn_completes(monkeypatch):
    """Happy path — single user turn returns response text."""
    client = MagicMock()
    client.messages.create.return_value = _mk_response(["hello"])
    _install_fake_anthropic(monkeypatch, client_factory=lambda **_: client)

    provider = AnthropicProvider(api_key="k")
    assert provider.complete([Message("user", "hi")]) == "hello"


def test_registered_in_global_registry():
    """Importing the module self-registers under key "claude"."""
    from palace.llm.base import PROVIDER_REGISTRY

    assert "claude" in PROVIDER_REGISTRY
