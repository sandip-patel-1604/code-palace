"""Uniform availability checks and degraded-mode rendering for LLM features.

Every LLM-backed command (plan --llm, explain, onboard, MCP plan tool)
funnels through :func:`check_availability` so the graceful-degradation
contract is enforced in exactly one place.
"""

from __future__ import annotations

from dataclasses import dataclass

# Import provider modules for their side-effect registration.
# These imports are kept at module load so the registry is populated
# before the first call to check_availability().
from palace.llm import anthropic as _anthropic  # noqa: F401
from palace.llm import ollama as _ollama  # noqa: F401
from palace.llm import openai as _openai  # noqa: F401
from palace.llm.base import LLMProvider, PROVIDER_REGISTRY


@dataclass
class LLMAvailability:
    """Outcome of :func:`check_availability`.

    When nothing is available, ``provider`` is None and ``reason`` explains why.
    """

    provider: LLMProvider | None
    provider_name: str | None
    model: str | None
    reason: str

    @property
    def is_available(self) -> bool:
        return self.provider is not None


_TRY_ORDER = ["claude", "openai", "ollama"]


def check_availability(prefer: str | None = None) -> LLMAvailability:
    """Return the first available LLM provider, or a degraded availability.

    Never raises. Never blocks longer than each provider's ``available()``
    implementation permits (Ollama uses a 2s probe).

    Parameters
    ----------
    prefer:
        If supplied, only try this provider. When it is not available, return
        a degraded availability rather than falling through to other providers.
        This matches the ``--provider`` CLI flag semantics.
    """
    keys = [prefer] if prefer else _TRY_ORDER
    reasons: list[str] = []

    for key in keys:
        factory = PROVIDER_REGISTRY.get(key)
        if factory is None:
            reasons.append(f"{key}: provider not registered")
            continue
        try:
            provider = factory()
        except Exception as e:
            reasons.append(f"{key}: constructor failed: {e}")
            continue
        try:
            if provider.available():
                model = getattr(provider, "_model", None)
                return LLMAvailability(
                    provider=provider,
                    provider_name=key,
                    model=model,
                    reason="",
                )
            reasons.append(f"{key}: not available")
        except Exception as e:
            reasons.append(f"{key}: probe failed: {e}")

    return LLMAvailability(
        provider=None,
        provider_name=None,
        model=None,
        reason="; ".join(reasons) or "no LLM providers configured",
    )


def render_degraded_notice(console, feature: str) -> None:
    """Print a uniform degraded-mode notice to *console*.

    Accepts any object with a ``print()`` method (rich.console.Console or a
    test double). Never raises.
    """
    console.print(
        f"\n  [dim]Note: {feature} is running in structural mode. "
        f"Set ANTHROPIC_API_KEY / OPENAI_API_KEY, or install Ollama, "
        f"for AI output.[/dim]"
    )
