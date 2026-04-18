"""FakeLLMProvider — deterministic LLM stub for unit tests.

Importing this module registers the "fake" provider in PROVIDER_REGISTRY so
tests can call ``get_provider("fake")`` without any further setup.
"""

from __future__ import annotations

from palace.llm.base import Message, register_provider


class FakeLLMProvider:
    """Deterministic, always-available LLM provider for tests.

    By default ``complete()`` returns ``f"{messages[-1].content}-response"``.
    Pass a ``responses`` dict mapping the last message's content to a canned
    reply for full control over the output.

    Constructor parameters
    ----------------------
    responses:
        Optional mapping from the last message's ``content`` to the reply
        string.  If the last content is not in the dict, the default
        ``"{content}-response"`` pattern is used.
    available_flag:
        Controls what ``available()`` returns.  Defaults to True so tests
        work without any env setup.
    """

    name: str = "fake"

    def __init__(
        self,
        responses: dict[str, str] | None = None,
        *,
        available_flag: bool = True,
    ) -> None:
        self._responses: dict[str, str] = responses or {}
        self._available_flag = available_flag

    def available(self) -> bool:
        """Return True by default; configurable via constructor."""
        return self._available_flag

    def complete(
        self,
        messages: list[Message],
        *,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> str:
        """Return a deterministic response based on the last message's content.

        Looks up ``messages[-1].content`` in the optional ``responses`` dict;
        falls back to ``f"{content}-response"`` if not found.
        """
        if not messages:
            return "-response"
        last_content = messages[-1].content
        return self._responses.get(last_content, f"{last_content}-response")


# ---------------------------------------------------------------------------
# Register at module import time
# ---------------------------------------------------------------------------

register_provider("fake", lambda: FakeLLMProvider())
