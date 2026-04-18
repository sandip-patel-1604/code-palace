"""Unit tests for palace.llm.ollama (T4)."""

from __future__ import annotations

import httpx
import pytest

from palace.core.exceptions import LLMError
from palace.llm.base import Message
from palace.llm.ollama import OllamaProvider


def _mock_transport(handler):
    """Build an httpx MockTransport from a handler and patch httpx module."""
    return httpx.MockTransport(handler)


def _patch_httpx(monkeypatch, handler):
    """Make module-level httpx.get/httpx.post use our mock transport."""
    import palace.llm.ollama as mod

    def fake_get(url, **kwargs):
        timeout = kwargs.pop("timeout", None)
        req = httpx.Request("GET", url)
        with httpx.Client(transport=_mock_transport(handler), timeout=timeout) as c:
            return c.send(req)

    def fake_post(url, **kwargs):
        timeout = kwargs.pop("timeout", None)
        json_body = kwargs.pop("json", None)
        with httpx.Client(transport=_mock_transport(handler), timeout=timeout) as c:
            return c.post(url, json=json_body)

    monkeypatch.setattr(mod.httpx, "get", fake_get)
    monkeypatch.setattr(mod.httpx, "post", fake_post)


def test_unavailable_when_offline(monkeypatch):
    """FM-1: Ollama not running → available() False."""
    def handler(req):
        raise httpx.ConnectError("refused")

    _patch_httpx(monkeypatch, handler)
    provider = OllamaProvider(host="http://localhost:11434")
    assert provider.available() is False


def test_non_streaming_request(monkeypatch):
    """FM-2: request body has stream=false."""
    captured = {}

    def handler(req):
        captured["body"] = req.read()
        return httpx.Response(200, json={"message": {"content": "ok"}})

    _patch_httpx(monkeypatch, handler)
    provider = OllamaProvider(host="http://localhost:11434")
    provider.complete([Message("user", "hi")])

    import json as _json
    parsed = _json.loads(captured["body"])
    assert parsed["stream"] is False


def test_model_not_found_raises(monkeypatch):
    """FM-3: 404 raises LLMError mentioning ollama pull."""
    def handler(req):
        return httpx.Response(404, text="model not found")

    _patch_httpx(monkeypatch, handler)
    provider = OllamaProvider(host="http://localhost:11434", model="missing")
    with pytest.raises(LLMError, match="ollama pull"):
        provider.complete([Message("user", "hi")])


def test_response_content_extracted(monkeypatch):
    """FM-4: extract message.content from response body."""
    def handler(req):
        return httpx.Response(200, json={"message": {"content": "hello"}})

    _patch_httpx(monkeypatch, handler)
    provider = OllamaProvider(host="http://localhost:11434")
    assert provider.complete([Message("user", "hi")]) == "hello"


def test_host_trailing_slash_normalized():
    """FM-5: trailing slash stripped."""
    p1 = OllamaProvider(host="http://localhost:11434")
    p2 = OllamaProvider(host="http://localhost:11434/")
    assert p1._host == p2._host == "http://localhost:11434"


def test_empty_messages_raises():
    provider = OllamaProvider()
    with pytest.raises(LLMError, match="no messages"):
        provider.complete([])


def test_malformed_response_raises(monkeypatch):
    def handler(req):
        return httpx.Response(200, json={"unexpected": "shape"})

    _patch_httpx(monkeypatch, handler)
    provider = OllamaProvider(host="http://localhost:11434")
    with pytest.raises(LLMError, match="malformed"):
        provider.complete([Message("user", "hi")])


def test_registered_in_global_registry():
    from palace.llm.base import PROVIDER_REGISTRY

    assert "ollama" in PROVIDER_REGISTRY
