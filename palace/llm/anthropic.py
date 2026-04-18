"""Anthropic Claude provider for Code Palace.

Implements the :class:`palace.llm.base.LLMProvider` protocol against
``anthropic.Anthropic``. The SDK import is lazy so that ``palace.llm`` can
be imported on machines without the ``anthropic`` package installed.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from palace.core.exceptions import LLMError
from palace.llm.base import Message, register_provider

logger = logging.getLogger("palace.llm.anthropic")

DEFAULT_MODEL = "claude-3-5-sonnet-latest"
_MAX_RETRIES = 3
_BACKOFF_BASE_S = 0.5


def _import_anthropic() -> Any:
    """Import the anthropic SDK or raise :class:`LLMError`.

    Kept as a function so tests can monkeypatch ``sys.modules``.
    """
    try:
        import anthropic  # noqa: PLC0415
    except ImportError as e:
        raise LLMError(
            "anthropic SDK not installed; pip install code-palace[llm]"
        ) from e
    return anthropic


class AnthropicProvider:
    """Claude provider using the official anthropic SDK."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._model = model or os.environ.get("PALACE_ANTHROPIC_MODEL", DEFAULT_MODEL)
        self._timeout_s = timeout_s
        self._client: Any | None = None

    @property
    def name(self) -> str:
        return "claude"

    def available(self) -> bool:
        if not self._api_key:
            return False
        try:
            _import_anthropic()
        except LLMError:
            return False
        return True

    def _get_client(self) -> Any:
        if self._client is None:
            anthropic = _import_anthropic()
            self._client = anthropic.Anthropic(
                api_key=self._api_key, timeout=self._timeout_s
            )
        return self._client

    def complete(
        self,
        messages: list[Message],
        *,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> str:
        if not messages:
            raise LLMError("no messages")

        anthropic = _import_anthropic()
        client = self._get_client()

        # Anthropic puts system messages in a separate `system=` kwarg, not in
        # the messages list. Extract and concatenate all system messages.
        system_parts = [m.content for m in messages if m.role == "system"]
        chat_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role != "system"
        ]
        system = "\n\n".join(system_parts) if system_parts else None

        for attempt in range(_MAX_RETRIES):
            try:
                kwargs: dict[str, Any] = {
                    "model": self._model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "messages": chat_messages,
                }
                if system is not None:
                    kwargs["system"] = system
                response = client.messages.create(**kwargs)
            except anthropic.RateLimitError as e:
                if attempt == _MAX_RETRIES - 1:
                    raise LLMError(f"anthropic rate limit after {_MAX_RETRIES} retries") from e
                time.sleep(_BACKOFF_BASE_S * (2**attempt))
                continue
            except Exception as e:
                raise LLMError(f"anthropic call failed: {e}") from e

            # Concatenate all text blocks in the response.
            parts: list[str] = []
            for block in getattr(response, "content", []) or []:
                if getattr(block, "type", None) == "text":
                    parts.append(getattr(block, "text", ""))
            return "".join(parts)

        # Should be unreachable — the loop either returns or raises.
        raise LLMError("anthropic: unexpected exit from retry loop")


register_provider("claude", lambda: AnthropicProvider())
