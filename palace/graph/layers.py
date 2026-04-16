"""Graph layer taxonomy for Code Palace analysis layers."""

from __future__ import annotations

from enum import StrEnum


class GraphLayer(StrEnum):
    """Conceptual layers of the code graph, ordered from static to dynamic."""

    STRUCTURAL = "structural"
    SYMBOLIC = "symbolic"
    RELATIONAL = "relational"
    SEMANTIC = "semantic"
    TEMPORAL = "temporal"
    BEHAVIORAL = "behavioral"
