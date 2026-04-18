"""MCP tool: palace_plan — structural change plan with optional LLM enrichment."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from palace.core.config import PalaceConfig
from palace.core.palace import Palace
from palace.graph.planner import PlanResult, StructuralPlanner
from palace.llm.availability import check_availability
from palace.llm.planner import EnrichedPlanResult, LLMPlanner

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "task": {
            "type": "string",
            "description": "Natural language task description.",
        },
        "scope": {
            "type": "string",
            "description": "Optional glob to restrict matched files.",
        },
        "no_llm": {
            "type": "boolean",
            "description": "Skip LLM enrichment.",
            "default": False,
        },
        "provider": {
            "type": "string",
            "description": "Force a specific LLM provider: claude, openai, or ollama.",
        },
    },
    "required": ["task"],
}


async def run(arguments: dict) -> str:
    task = arguments.get("task")
    if not task:
        return "Error: `task` is required."
    scope = arguments.get("scope")
    no_llm = bool(arguments.get("no_llm", False))
    provider = arguments.get("provider")

    config = PalaceConfig.discover(path=Path.cwd())
    if config is None:
        return "Error: No palace found. Run `palace init` first."

    palace = Palace(config)
    palace.open()
    try:
        assert palace.store is not None
        structural = StructuralPlanner(palace.store).plan(task, scope=scope)
    finally:
        palace.close()

    result: PlanResult | EnrichedPlanResult = structural
    if not no_llm:
        availability = check_availability(prefer=provider)
        if availability.is_available and availability.provider is not None:
            result = LLMPlanner(availability.provider).enrich(structural)

    return _format(result)


def _format(result: PlanResult | EnrichedPlanResult) -> str:
    lines: list[str] = []
    title = "Change Plan" if isinstance(result, EnrichedPlanResult) else "Structural Change Plan"
    lines.append(f'# {title}: "{result.task}"')
    lines.append("")

    if isinstance(result, EnrichedPlanResult) and result.rationale:
        lines.append(f"**Risk:** {result.risk}")
        lines.append(f"**Provider:** {result.llm_provider}")
        lines.append("")
        lines.append(result.rationale)
        lines.append("")

    if result.keywords:
        lines.append(f"**Keywords:** {', '.join(result.keywords)}")
        lines.append("")

    if not result.matched_files:
        lines.append("_No matching files found. Try a more specific task description._")
        return "\n".join(lines)

    if result.patterns:
        lines.append("## Detected Patterns")
        for pat in result.patterns:
            lines.append(f"- **{pat.name}** in `{pat.directory}`")
        lines.append("")

    lines.append("## Files Likely Involved")
    lines.append("")
    for idx, mf in enumerate(result.matched_files, start=1):
        lines.append(f"{idx}. `{mf.path}` — score {mf.relevance_score}")
        syms = ", ".join(s.get("name", "") for s in mf.matched_symbols[:5])
        if syms:
            lines.append(f"   - Matched: {syms}")
        if mf.reason:
            lines.append(f"   - Reason: {mf.reason}")

    if result.suggested_tests:
        lines.append("")
        lines.append("## Related Tests")
        for t in result.suggested_tests:
            lines.append(f"- `{t}`")

    return "\n".join(lines)
