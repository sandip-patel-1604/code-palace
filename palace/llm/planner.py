"""LLM-enriched change planner (T7).

Wraps a ``PlanResult`` from :class:`palace.graph.planner.StructuralPlanner`
with rationale, ordered steps, and a risk assessment produced by an LLM.
Falls back silently to the structural result when no provider is available.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from palace.core.exceptions import LLMError
from palace.graph.planner import PlanResult
from palace.llm.base import LLMProvider, Message
from palace.llm.prompts.plan import (
    PLAN_SYSTEM,
    build_user_message,
    parse_risk,
)


@dataclass
class EnrichedPlanResult:
    """Structural PlanResult with LLM-added narrative fields."""

    task: str
    matched_files: list = field(default_factory=list)
    patterns: list = field(default_factory=list)
    suggested_tests: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    rationale: str = ""
    risk: str = "UNKNOWN"
    llm_provider: str = ""

    @classmethod
    def from_structural(
        cls, result: PlanResult, rationale: str, risk: str, llm_provider: str
    ) -> "EnrichedPlanResult":
        return cls(
            task=result.task,
            matched_files=result.matched_files,
            patterns=result.patterns,
            suggested_tests=result.suggested_tests,
            keywords=result.keywords,
            rationale=rationale,
            risk=risk,
            llm_provider=llm_provider,
        )


class LLMPlanner:
    """Enrich a structural ``PlanResult`` using an LLM."""

    def __init__(self, provider: LLMProvider, max_files: int = 10) -> None:
        self.provider = provider
        self.max_files = max_files

    def enrich(self, structural: PlanResult) -> EnrichedPlanResult:
        """Return an enriched result; never raises.

        If the structural result has no matched files, returns a pass-through
        enriched result without calling the LLM.
        If the LLM call fails, returns a pass-through with rationale explaining
        the failure.
        """
        if not structural.matched_files:
            return EnrichedPlanResult.from_structural(
                structural,
                rationale="",
                risk="UNKNOWN",
                llm_provider=self.provider.name,
            )

        user_msg = build_user_message(
            structural.task,
            structural.keywords,
            structural.matched_files,
            structural.patterns,
            structural.suggested_tests,
            max_files=self.max_files,
        )

        try:
            text = self.provider.complete(
                [
                    Message("system", PLAN_SYSTEM),
                    Message("user", user_msg),
                ]
            )
        except LLMError as e:
            return EnrichedPlanResult.from_structural(
                structural,
                rationale=f"LLM unavailable: {e}",
                risk="UNKNOWN",
                llm_provider=self.provider.name,
            )

        return EnrichedPlanResult.from_structural(
            structural,
            rationale=text.strip(),
            risk=parse_risk(text),
            llm_provider=self.provider.name,
        )
