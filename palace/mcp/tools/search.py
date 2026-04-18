"""MCP tool: palace_search — semantic code search using local embeddings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from palace.core.config import PalaceConfig
from palace.core.palace import Palace
from palace.semantic.embeddings import MockEmbeddingEngine
from palace.semantic.search import SemanticSearch

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Natural language search query.",
        },
        "kind": {
            "type": "string",
            "description": "Filter by symbol kind: function, class, method.",
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of results.",
            "default": 20,
        },
    },
    "required": ["query"],
}


async def run(arguments: dict) -> str:
    query = arguments.get("query")
    if not query:
        return "Error: `query` is required."
    kind = arguments.get("kind")
    limit = int(arguments.get("limit", 20))

    config = PalaceConfig.discover(path=Path.cwd())
    if config is None:
        return "Error: No palace found. Run `palace init` first."

    palace = Palace(config)
    palace.open()
    try:
        engine = MockEmbeddingEngine()
        searcher = SemanticSearch(palace.vector_store, engine)
        if not searcher.available():
            return "Error: Embeddings not computed. Run `palace init` to index embeddings."
        results = searcher.search(query, limit=limit, kind=kind)
        root = str(palace.config.root)
    finally:
        palace.close()

    if not results:
        return f"No results for: {query}"

    lines: list[str] = [f"# Search Results for: {query}", ""]
    for r in results:
        score = r.get("score", 0)
        kind_str = r.get("kind", "")
        name = r.get("name", r.get("path", ""))
        file_path = r.get("file_path", r.get("path", ""))
        if file_path.startswith(root + "/"):
            file_path = file_path[len(root) + 1:]
        lines.append(f"- [{score:.2f}] **{kind_str}** `{name}` — `{file_path}`")
    return "\n".join(lines)
