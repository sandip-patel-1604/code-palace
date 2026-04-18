"""MCP tool: palace_explain — natural-language explanation of a file or directory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from palace.core.config import PalaceConfig
from palace.core.palace import Palace
from palace.core.resolve import resolve_file_target
from palace.graph.patterns import PatternDetector
from palace.llm.availability import check_availability
from palace.llm.explainer import Explainer, ExplanationContext

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "target": {
            "type": "string",
            "description": "File path or directory to explain (relative to project root).",
        },
        "no_llm": {
            "type": "boolean",
            "description": "Force structural output (skip LLM).",
            "default": False,
        },
        "provider": {
            "type": "string",
            "description": "Force a specific LLM provider: claude, openai, or ollama.",
        },
    },
    "required": ["target"],
}


async def run(arguments: dict) -> str:
    target = arguments.get("target")
    if not target:
        return "Error: `target` is required."
    no_llm = bool(arguments.get("no_llm", False))
    provider = arguments.get("provider")

    config = PalaceConfig.discover(path=Path.cwd())
    if config is None:
        return "Error: No palace found. Run `palace init` first."

    palace = Palace(config)
    palace.open()
    try:
        assert palace.store is not None
        store = palace.store
        root = palace.config.root

        file_row = resolve_file_target(store, target, root)
        files: list[dict] = []
        if file_row is not None:
            files = [file_row]
        else:
            target_norm = target.rstrip("/")
            for f in store.get_all_files():
                p = f["path"]
                if p == target_norm or p.startswith(target_norm + "/"):
                    files.append(f)

        if not files:
            return f"Error: `{target}` not found in the index. Run `palace init` to re-index."

        symbols: list[dict] = []
        for f in files:
            symbols.extend(store.get_symbols(file_id=f["file_id"]))

        concerns = PatternDetector(store).detect_cross_cutting()
        ctx = ExplanationContext(
            target=target, files=files, symbols=symbols, concerns=concerns
        )

        provider_obj = None
        if not no_llm:
            availability = check_availability(prefer=provider)
            if availability.is_available:
                provider_obj = availability.provider

        explanation = Explainer(provider_obj).explain(ctx)
    finally:
        palace.close()

    return explanation.text
