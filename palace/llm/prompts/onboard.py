"""Prompt templates for palace onboard (T9)."""

from __future__ import annotations

ONBOARD_SYSTEM = """You are an onboarding mentor producing a "Codebase Tour"
document for a new engineer joining a project analysed by Code Palace.

Rules:
- Produce Markdown with sections: "## Codebase Tour", "## Architecture Overview",
  "## Domains", "## Getting Started", "## Gotchas".
- Use the domain, file, and pattern data supplied; do not invent module names.
- Keep under 800 words.
- Do not wrap output in ``` fences.
"""


ONBOARD_USER_TEMPLATE = """Project root: {root}
Total files indexed: {file_count}
Total symbols: {symbol_count}

Domains:
{domains_block}

Top entry points (most depended-on):
{entry_points_block}

Cross-cutting concerns:
{concerns_block}

Naming patterns:
{patterns_block}

Produce the onboarding tour now.
"""


def build_onboard_message(
    root: str,
    file_count: int,
    symbol_count: int,
    domains: list[dict],
    entry_points: list[dict],
    concerns: list,
    patterns: list,
    max_per_domain: int = 10,
) -> str:
    """Render the onboarding prompt, truncating per-domain file samples."""
    domain_lines = []
    for d in domains[:20]:
        sample_files = d.get("sample_files", [])[:max_per_domain]
        samples = ", ".join(f"`{p}`" for p in sample_files) or "no sample files"
        domain_lines.append(
            f"- **{d.get('name', '(unnamed)')}**: {samples}"
        )

    ep_lines = [
        f"- `{ep['path']}` ({ep.get('dependent_count', 0)} dependents)"
        for ep in entry_points[:10]
    ]

    concern_lines = [
        f"- {c.kind} ({c.call_site_count} call-sites)"
        for c in concerns[:10]
    ]

    pattern_lines = [f"- {p.name} in `{p.directory}`" for p in patterns[:10]]

    return ONBOARD_USER_TEMPLATE.format(
        root=root,
        file_count=file_count,
        symbol_count=symbol_count,
        domains_block="\n".join(domain_lines) or "none (run `palace init` with domain clustering)",
        entry_points_block="\n".join(ep_lines) or "none",
        concerns_block="\n".join(concern_lines) or "none",
        patterns_block="\n".join(pattern_lines) or "none",
    )
