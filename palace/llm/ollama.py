"""Ollama local provider for Code Palace.

Uses :mod:`httpx` (a required palace dep) to talk to a local Ollama daemon.
No API key is needed. When Ollama is not running, ``available()`` returns
False within a short timeout so CLI startup never blocks.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from palace.core.exceptions import LLMError
from palace.llm.base import Message, register_provider

logger = logging.getLogger("palace.llm.ollama")

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5-coder:7b"
_PROBE_TIMEOUT_S = 2.0


def _normalize_host(host: str) -> str:
    """Strip trailing slashes so URL joins don't double up."""
    return host.rstrip("/")


class OllamaProvider:
    """Provider that talks to a local Ollama daemon over HTTP."""

    def __init__(
        self,
        host: str | None = None,
        model: str | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        self._host = _normalize_host(host or os.environ.get("OLLAMA_HOST", DEFAULT_HOST))
        self._model = model or os.environ.get("PALACE_OLLAMA_MODEL", DEFAULT_MODEL)
        self._timeout_s = timeout_s

    @property
    def name(self) -> str:
        return "ollama"

    def available(self) -> bool:
        """Probe /api/tags with a short timeout; any error → unavailable."""
        try:
            r = httpx.get(f"{self._host}/api/tags", timeout=_PROBE_TIMEOUT_S)
            return r.status_code == 200
        except Exception:
            return False

    def complete(
        self,
        messages: list[Message],
        *,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> str:
        if not messages:
            raise LLMError("no messages")

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }

        try:
            r = httpx.post(
                f"{self._host}/api/chat",
                json=payload,
                timeout=self._timeout_s,
            )
        except httpx.HTTPError as e:
            raise LLMError(f"ollama request failed: {e}") from e

        if r.status_code == 404:
            raise LLMError(
                f"ollama: model '{self._model}' not pulled. "
                f"Run: ollama pull {self._model}"
            )
        if r.status_code >= 400:
            raise LLMError(f"ollama returned {r.status_code}: {r.text[:200]}")

        try:
            body = r.json()
            return body["message"]["content"]
        except (KeyError, ValueError) as e:
            raise LLMError(f"ollama: malformed response: {e}") from e


register_provider("ollama", lambda: OllamaProvider())
