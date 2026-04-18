"""Prompt templates for palace explain (T8)."""

from __future__ import annotations

EXPLAIN_SYSTEM = """You are a senior engineer onboarding a new teammate to a
codebase through the Code Palace CLI. You receive a structural summary of a
file or directory and must produce a concise natural-language explanation.

Rules:
- Output sections: "Overview", "Key Symbols", "How It Fits".
- Keep under 400 words.
- Only reference the symbols and files provided — do not invent identifiers.
- Do not wrap the output in ``` fences.
"""


EXPLAIN_USER_TEMPLATE = """Target: {target}

Files:
{files_block}

Top-level symbols:
{symbols_block}

Cross-cutting concerns (from pattern detector):
{concerns_block}

Produce the explanation now.
"""


def build_explain_message(
    target: str,
    files: list[dict],
    symbols: list[dict],
    concerns: list,
    max_bytes: int = 32_000,
) -> str:
    """Build the user message; truncates to ``max_bytes`` bytes."""
    file_lines = [f"- `{f['path']}` ({f.get('language', '?')})" for f in files[:50]]
    sym_lines = []
    for s in symbols[:200]:
        doc = (s.get("docstring") or "").strip().replace("\n", " ")[:120]
        sym_lines.append(
            f"- {s['kind']} `{s['name']}`{(': ' + doc) if doc else ''}"
        )
    concern_lines = [
        f"- {c.kind} ({c.call_site_count} call-sites across {len(c.affected_files)} files)"
        for c in concerns[:10]
    ]
    msg = EXPLAIN_USER_TEMPLATE.format(
        target=target,
        files_block="\n".join(file_lines) or "none",
        symbols_block="\n".join(sym_lines) or "none",
        concerns_block="\n".join(concern_lines) or "none",
    )
    encoded = msg.encode("utf-8")
    if len(encoded) > max_bytes:
        msg = encoded[:max_bytes].decode("utf-8", errors="ignore") + "\n... [truncated]"
    return msg
