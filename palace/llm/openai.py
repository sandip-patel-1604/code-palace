"""OpenAI provider for Code Palace."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from palace.core.exceptions import LLMError
from palace.llm.base import Message, register_provider

logger = logging.getLogger("palace.llm.openai")

DEFAULT_MODEL = "gpt-4o-mini"
_MAX_RETRIES = 3
_BACKOFF_BASE_S = 0.5


def _import_openai() -> Any:
    """Import the openai SDK or raise :class:`LLMError`."""
    try:
        import openai  # noqa: PLC0415
    except ImportError as e:
        raise LLMError(
            "openai SDK not installed; pip install code-palace[llm]"
        ) from e
    return openai


class OpenAIProvider:
    """OpenAI chat-completions provider."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._model = model or os.environ.get("PALACE_OPENAI_MODEL", DEFAULT_MODEL)
        self._timeout_s = timeout_s
        self._client: Any | None = None

    @property
    def name(self) -> str:
        return "openai"

    def available(self) -> bool:
        if not self._api_key:
            return False
        try:
            _import_openai()
        except LLMError:
            return False
        return True

    def _get_client(self) -> Any:
        if self._client is None:
            openai = _import_openai()
            self._client = openai.OpenAI(
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

        openai = _import_openai()
        client = self._get_client()
        chat_messages = [{"role": m.role, "content": m.content} for m in messages]

        for attempt in range(_MAX_RETRIES):
            try:
                response = client.chat.completions.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=chat_messages,
                )
            except openai.RateLimitError as e:
                if attempt == _MAX_RETRIES - 1:
                    raise LLMError(f"openai rate limit after {_MAX_RETRIES} retries") from e
                time.sleep(_BACKOFF_BASE_S * (2**attempt))
                continue
            except Exception as e:
                raise LLMError(f"openai call failed: {e}") from e

            try:
                content = response.choices[0].message.content
            except (AttributeError, IndexError) as e:
                raise LLMError(f"openai: malformed response: {e}") from e
            if content is None:
                raise LLMError("empty completion")
            return content

        raise LLMError("openai: unexpected exit from retry loop")


register_provider("openai", lambda: OpenAIProvider())
