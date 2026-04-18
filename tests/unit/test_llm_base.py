"""T1 gate tests — LLM provider abstraction and FakeLLMProvider validation."""

from __future__ import annotations

import sys
from typing import Callable

import pytest

from palace.llm.base import (
    LLMProvider,
    Message,
    PROVIDER_REGISTRY,
    get_provider,
    register_provider,
)
from tests.fakes.fake_llm import FakeLLMProvider


# ---------------------------------------------------------------------------
# FM-1: Protocol shape
# ---------------------------------------------------------------------------


class TestProviderProtocolShape:
    """FM-1 — FakeLLMProvider must satisfy the LLMProvider Protocol at runtime."""

    def test_provider_protocol_shape(self) -> None:
        """isinstance(FakeLLMProvider(), LLMProvider) must be True."""
        assert isinstance(FakeLLMProvider(), LLMProvider)


# ---------------------------------------------------------------------------
# FM-2: No env vars → returns None
# ---------------------------------------------------------------------------


class TestNoEnvReturnsNone:
    """FM-2 — get_provider() returns None when no env vars are set."""

    def test_no_env_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With ANTHROPIC_API_KEY, OPENAI_API_KEY, and PALACE_LLM_PROVIDER unset
        and no claude/openai/ollama entries in the registry, get_provider()
        must return None rather than raising.
        """
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("PALACE_LLM_PROVIDER", raising=False)

        # Temporarily remove well-known providers from registry so auto-detect
        # has nothing to try.
        saved: dict[str, Callable] = {}
        for key in ("claude", "openai", "ollama"):
            if key in PROVIDER_REGISTRY:
                saved[key] = PROVIDER_REGISTRY.pop(key)

        try:
            result = get_provider()
            assert result is None
        finally:
            PROVIDER_REGISTRY.update(saved)


# ---------------------------------------------------------------------------
# FM-3: Explicit unavailable provider → returns None
# ---------------------------------------------------------------------------


class TestExplicitUnavailableReturnsNone:
    """FM-3 — get_provider("claude") with no key returns None."""

    def test_explicit_unavailable_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get_provider("claude") returns None when ANTHROPIC_API_KEY is absent
        and the claude provider is not registered (or its available() is False).
        """
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        # Remove claude from registry if it was registered.
        saved = PROVIDER_REGISTRY.pop("claude", None)
        try:
            result = get_provider("claude")
            assert result is None
        finally:
            if saved is not None:
                PROVIDER_REGISTRY["claude"] = saved


# ---------------------------------------------------------------------------
# FM-4: Lazy SDK import
# ---------------------------------------------------------------------------


class TestLazySdkImport:
    """FM-4 — palace.llm.base must be importable even without anthropic/openai."""

    def test_lazy_sdk_import(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Simulate anthropic and openai not being installed by hiding them in
        sys.modules, then re-import palace.llm.base to confirm no ImportError.
        """
        monkeypatch.setitem(sys.modules, "anthropic", None)  # type: ignore[arg-type]
        monkeypatch.setitem(sys.modules, "openai", None)  # type: ignore[arg-type]

        # Remove cached module so the import statement executes fresh.
        base_mod = sys.modules.pop("palace.llm.base", None)
        try:
            import importlib

            importlib.import_module("palace.llm.base")
        except ImportError as exc:
            pytest.fail(f"palace.llm.base raised ImportError: {exc}")
        finally:
            # Restore original module if it existed.
            if base_mod is not None:
                sys.modules["palace.llm.base"] = base_mod


# ---------------------------------------------------------------------------
# FM-5: Registry idempotency
# ---------------------------------------------------------------------------


class TestRegistryIdempotent:
    """FM-5 — register_provider called twice does not grow registry."""

    def test_registry_idempotent(self) -> None:
        """Registering the same key twice leaves registry length delta == 1."""
        key = "_test_idempotent_key_"
        factory = lambda: FakeLLMProvider()  # noqa: E731

        # Clean up before test.
        PROVIDER_REGISTRY.pop(key, None)
        initial_len = len(PROVIDER_REGISTRY)

        register_provider(key, factory)
        after_first = len(PROVIDER_REGISTRY)

        register_provider(key, factory)
        after_second = len(PROVIDER_REGISTRY)

        # Clean up.
        PROVIDER_REGISTRY.pop(key, None)

        assert after_first == initial_len + 1, "First registration should add 1"
        assert after_second == after_first, "Second registration must not add another entry"


# ---------------------------------------------------------------------------
# Fake provider round-trip
# ---------------------------------------------------------------------------


class TestFakeProviderRoundtrip:
    """Verify FakeLLMProvider default response format."""

    def test_fake_provider_roundtrip(self) -> None:
        """FakeLLMProvider().complete([Message("user","hi")]) returns "hi-response"."""
        provider = FakeLLMProvider()
        result = provider.complete([Message(role="user", content="hi")])
        assert result == "hi-response"


# ---------------------------------------------------------------------------
# get_provider("fake") via registry
# ---------------------------------------------------------------------------


class TestPreferFakeViaRegistry:
    """Verify that get_provider("fake") resolves to an available FakeLLMProvider."""

    def test_prefer_fake_via_registry(self) -> None:
        """After importing tests.fakes.fake_llm the "fake" key is in the registry.
        get_provider("fake") should return a FakeLLMProvider whose available() is True.
        """
        # tests.fakes.fake_llm is already imported at the top of this module,
        # which registers "fake" in PROVIDER_REGISTRY at import time.
        result = get_provider("fake")
        assert result is not None
        assert isinstance(result, FakeLLMProvider)
        assert result.available() is True
