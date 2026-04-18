"""LLM-backed explanation of a file or directory (T8)."""

from __future__ import annotations

from dataclasses import dataclass, field

from palace.core.exceptions import LLMError
from palace.llm.base import LLMProvider, Message
from palace.llm.prompts.explain import EXPLAIN_SYSTEM, build_explain_message


@dataclass
class ExplanationContext:
    """Structured context gathered before prompting the LLM."""

    target: str
    files: list[dict] = field(default_factory=list)
    symbols: list[dict] = field(default_factory=list)
    concerns: list = field(default_factory=list)


@dataclass
class Explanation:
    target: str
    text: str
    llm_provider: str
    structural_only: bool = False


class Explainer:
    def __init__(self, provider: LLMProvider | None) -> None:
        self.provider = provider

    def explain(self, ctx: ExplanationContext) -> Explanation:
        """Produce an explanation; falls back to a structural summary on error."""
        if self.provider is None:
            return Explanation(
                target=ctx.target,
                text=self._structural_fallback(ctx),
                llm_provider="",
                structural_only=True,
            )

        if not ctx.files and not ctx.symbols:
            return Explanation(
                target=ctx.target,
                text=f"No indexed content for `{ctx.target}`.",
                llm_provider=self.provider.name,
                structural_only=True,
            )

        user = build_explain_message(ctx.target, ctx.files, ctx.symbols, ctx.concerns)
        try:
            text = self.provider.complete(
                [Message("system", EXPLAIN_SYSTEM), Message("user", user)]
            )
        except LLMError as e:
            return Explanation(
                target=ctx.target,
                text=f"{self._structural_fallback(ctx)}\n\n_LLM unavailable: {e}_",
                llm_provider=self.provider.name,
                structural_only=True,
            )

        return Explanation(
            target=ctx.target,
            text=_strip_fences(text.strip()),
            llm_provider=self.provider.name,
            structural_only=False,
        )

    @staticmethod
    def _structural_fallback(ctx: ExplanationContext) -> str:
        lines = [f"# {ctx.target}", ""]
        lines.append(f"**Files:** {len(ctx.files)}")
        lines.append(f"**Symbols:** {len(ctx.symbols)}")
        if ctx.files:
            lines.append("")
            lines.append("## Files")
            for f in ctx.files[:20]:
                lines.append(f"- `{f['path']}`")
        if ctx.symbols:
            lines.append("")
            lines.append("## Top Symbols")
            for s in ctx.symbols[:20]:
                lines.append(f"- {s['kind']} `{s['name']}`")
        return "\n".join(lines)


def _strip_fences(text: str) -> str:
    """Remove leading/trailing ```/```markdown fences from LLM output."""
    t = text.strip()
    if t.startswith("```"):
        first_nl = t.find("\n")
        if first_nl != -1:
            t = t[first_nl + 1:]
    if t.endswith("```"):
        t = t[: -3].rstrip()
    return t
