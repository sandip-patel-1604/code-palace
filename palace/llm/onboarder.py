"""LLM-backed codebase onboarding tour (T9)."""

from __future__ import annotations

from dataclasses import dataclass, field

from palace.core.exceptions import LLMError
from palace.llm.base import LLMProvider, Message
from palace.llm.explainer import _strip_fences
from palace.llm.prompts.onboard import ONBOARD_SYSTEM, build_onboard_message


@dataclass
class OnboardContext:
    root: str = ""
    file_count: int = 0
    symbol_count: int = 0
    domains: list[dict] = field(default_factory=list)
    entry_points: list[dict] = field(default_factory=list)
    concerns: list = field(default_factory=list)
    patterns: list = field(default_factory=list)


@dataclass
class OnboardTour:
    text: str
    llm_provider: str
    structural_only: bool = False


class Onboarder:
    def __init__(self, provider: LLMProvider | None) -> None:
        self.provider = provider

    def generate(self, ctx: OnboardContext) -> OnboardTour:
        if self.provider is None:
            return OnboardTour(
                text=self._structural_fallback(ctx),
                llm_provider="",
                structural_only=True,
            )

        user = build_onboard_message(
            ctx.root,
            ctx.file_count,
            ctx.symbol_count,
            ctx.domains,
            ctx.entry_points,
            ctx.concerns,
            ctx.patterns,
        )
        try:
            text = self.provider.complete(
                [Message("system", ONBOARD_SYSTEM), Message("user", user)]
            )
        except LLMError as e:
            return OnboardTour(
                text=f"{self._structural_fallback(ctx)}\n\n_LLM unavailable: {e}_",
                llm_provider=self.provider.name,
                structural_only=True,
            )
        return OnboardTour(
            text=_strip_fences(text.strip()),
            llm_provider=self.provider.name,
            structural_only=False,
        )

    @staticmethod
    def _structural_fallback(ctx: OnboardContext) -> str:
        lines = ["# Codebase Tour", ""]
        lines.append(f"**Root:** `{ctx.root}`")
        lines.append(f"**Files:** {ctx.file_count}   **Symbols:** {ctx.symbol_count}")
        lines.append("")
        if ctx.domains:
            lines.append("## Domains")
            for d in ctx.domains[:20]:
                lines.append(f"- **{d.get('name', '(unnamed)')}**")
            lines.append("")
        else:
            lines.append(
                "_No domain clusters computed. "
                "Run `palace init` with domain clustering enabled._"
            )
            lines.append("")
        if ctx.entry_points:
            lines.append("## Top Entry Points")
            for ep in ctx.entry_points[:10]:
                lines.append(f"- `{ep['path']}`")
            lines.append("")
        if ctx.concerns:
            lines.append("## Cross-Cutting Concerns")
            for c in ctx.concerns[:10]:
                lines.append(f"- {c.kind}")
            lines.append("")
        return "\n".join(lines)
