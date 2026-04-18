"""Prompt templates for LLM-enriched change plans (T7)."""

from __future__ import annotations

PLAN_SYSTEM = """You are an expert software architect embedded in the Code Palace CLI.
You receive a structural change plan produced by static graph analysis and must
produce a concrete, actionable change plan in Markdown.

Rules:
- Only reference files and symbols the structural plan lists. Never invent code paths.
- Output three clearly-labelled sections: "Rationale", "Ordered Steps", "Risk".
- Risk must be exactly one of: LOW, MEDIUM, HIGH.
- Keep output under 600 words.
- Do not wrap output in ``` fences.
"""


PLAN_USER_TEMPLATE = """Task: {task}

Keywords: {keywords}

Candidate files (ranked by structural relevance):
{matched_files}

Detected patterns:
{patterns}

Related tests:
{suggested_tests}

Produce the change plan now.
"""


def build_user_message(
    task: str,
    keywords: list[str],
    matched_files: list,
    patterns: list,
    suggested_tests: list[str],
    max_files: int = 10,
) -> str:
    """Render the user message from a structural plan result.

    Caps ``matched_files`` to ``max_files`` to keep the prompt bounded.
    """
    file_lines = []
    for mf in matched_files[:max_files]:
        syms = ", ".join(s.get("name", "") for s in mf.matched_symbols[:5])
        file_lines.append(
            f"- `{mf.path}` (score {mf.relevance_score}, "
            f"matched: {syms or 'n/a'})"
        )
    pattern_lines = [
        f"- {p.name} in `{p.directory}`: {', '.join(p.examples[:3])}"
        for p in patterns
    ]
    tests_str = ", ".join(f"`{t}`" for t in suggested_tests[:10]) or "none"

    return PLAN_USER_TEMPLATE.format(
        task=task,
        keywords=", ".join(keywords) or "n/a",
        matched_files="\n".join(file_lines) or "none",
        patterns="\n".join(pattern_lines) or "none",
        suggested_tests=tests_str,
    )


def parse_risk(text: str) -> str:
    """Extract the risk level from the LLM output; default to UNKNOWN."""
    upper = text.upper()
    for level in ("HIGH", "MEDIUM", "LOW"):
        if f"RISK: {level}" in upper or f"RISK\n{level}" in upper or f"RISK:\n{level}" in upper:
            return level
        if f"**RISK**" in upper and level in upper.split("**RISK**", 1)[1][:100]:
            return level
    return "UNKNOWN"
