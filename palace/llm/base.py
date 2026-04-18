"""LLM provider abstraction, registry, and configuration for Code Palace.

This module is intentionally free of hard dependencies on anthropic/openai/ollama
so that ``import palace.llm.base`` never fails even when those SDKs are absent.
Concrete provider implementations live in sibling modules (T2/T3/T4).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Literal, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Message:
    """An immutable chat message with a role and content."""

    role: Literal["system", "user", "assistant"]
    content: str


# ---------------------------------------------------------------------------
# LLMProvider Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol that every LLM backend must satisfy.

    Being ``@runtime_checkable`` allows ``isinstance(obj, LLMProvider)``
    checks even without explicit inheritance — any class that implements
    ``name``, ``available()``, and ``complete()`` satisfies the protocol.
    """

    @property
    def name(self) -> str:
        """Short identifier for this provider (e.g. "claude", "openai")."""
        ...

    def available(self) -> bool:
        """Return True iff this provider can currently serve requests."""
        ...

    def complete(
        self,
        messages: list[Message],
        *,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> str:
        """Send ``messages`` to the LLM and return the assistant reply text."""
        ...


# ---------------------------------------------------------------------------
# LLMConfig
# ---------------------------------------------------------------------------


@dataclass
class LLMConfig:
    """Flat configuration bag passed to LLM provider constructors."""

    provider: str | None = None
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    max_tokens: int = 2048
    temperature: float = 0.2
    timeout_s: float = 60.0


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

# Maps provider key (e.g. "claude") to a zero-arg factory that returns an
# LLMProvider instance.  Populated by concrete provider modules at import
# time and by tests via register_provider().
PROVIDER_REGISTRY: dict[str, Callable[[], LLMProvider]] = {}


def register_provider(key: str, factory: Callable[[], LLMProvider]) -> None:
    """Register (or silently overwrite) a provider factory under *key*.

    Calling this twice with the same key replaces the factory but does **not**
    grow the registry — len(PROVIDER_REGISTRY) is unchanged after the second
    call (FM-5).
    """
    PROVIDER_REGISTRY[key] = factory


def get_provider(preferred: str | None = None) -> LLMProvider | None:
    """Return an available LLMProvider or None.

    Resolution order
    ----------------
    1. If *preferred* is given: look it up in the registry, instantiate,
       return if ``available()`` is True — otherwise return None.
    2. Check ``PALACE_LLM_PROVIDER`` env var; use it as the preferred key.
    3. Try well-known providers in order:
       - ``"claude"``  (requires ``ANTHROPIC_API_KEY``)
       - ``"openai"``  (requires ``OPENAI_API_KEY``)
       - ``"ollama"``  (always attempted; the provider checks reachability)
    4. Return None if nothing is available (FM-2).

    This function never raises — missing keys and unavailable providers are
    silently skipped (FM-3, FM-4).
    """
    if preferred is not None:
        try:
            factory = PROVIDER_REGISTRY[preferred]
            provider = factory()
            if provider.available():
                return provider
        except Exception:
            pass
        return None

    # Check env-var override.
    env_preferred = os.environ.get("PALACE_LLM_PROVIDER")
    if env_preferred:
        return get_provider(env_preferred)

    # Auto-detect: try well-known providers in priority order.
    _AUTO_DETECT_ORDER = [
        ("claude", "ANTHROPIC_API_KEY"),
        ("openai", "OPENAI_API_KEY"),
        ("ollama", None),  # No key required; provider checks reachability.
    ]

    for key, env_var in _AUTO_DETECT_ORDER:
        # Skip providers whose required env var is absent.
        if env_var and not os.environ.get(env_var):
            continue
        try:
            factory = PROVIDER_REGISTRY[key]
            provider = factory()
            if provider.available():
                return provider
        except Exception:
            continue

    return None
