"""Unit tests for palace.llm.planner (T7)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from palace.core.exceptions import LLMError
from palace.graph.planner import DetectedPattern, MatchedFile, PlanResult
from palace.llm.planner import EnrichedPlanResult, LLMPlanner
from palace.llm.prompts.plan import build_user_message, parse_risk


def _structural(matched: list[MatchedFile] | None = None) -> PlanResult:
    return PlanResult(
        task="add rate limiter",
        keywords=["rate", "limiter"],
        matched_files=matched or [],
        patterns=[],
        suggested_tests=[],
    )


def _file(path: str = "app/api.py", score: float = 5.0) -> MatchedFile:
    return MatchedFile(
        file_id=1,
        path=path,
        language="python",
        relevance_score=score,
        matched_symbols=[{"name": "handle_request", "kind": "function"}],
    )


def test_empty_structural_no_enrichment():
    """FM-2: no matched files → no LLM call."""
    provider = MagicMock()
    provider.name = "fake"
    result = LLMPlanner(provider).enrich(_structural())
    assert isinstance(result, EnrichedPlanResult)
    assert provider.complete.call_count == 0


def test_llm_error_falls_back():
    """FM-3: LLM error captured in rationale, no exception raised."""
    provider = MagicMock()
    provider.name = "fake"
    provider.complete.side_effect = LLMError("network down")

    result = LLMPlanner(provider).enrich(_structural([_file()]))
    assert result.risk == "UNKNOWN"
    assert "network down" in result.rationale


def test_llm_output_captured():
    """Happy path — LLM output stored on result."""
    provider = MagicMock()
    provider.name = "fake"
    provider.complete.return_value = (
        "Rationale: add middleware at the edge.\n"
        "Ordered Steps: 1. Add limiter. 2. Wire middleware.\n"
        "Risk: LOW"
    )

    result = LLMPlanner(provider).enrich(_structural([_file()]))
    assert result.risk == "LOW"
    assert "middleware" in result.rationale
    assert result.llm_provider == "fake"


def test_prompt_truncation_cap():
    """FM-4: matched_files capped by max_files."""
    many = [_file(path=f"m/{i}.py") for i in range(50)]
    msg = build_user_message("t", [], many, [], [], max_files=10)
    assert msg.count("\n- `") == 10


def test_parse_risk_medium():
    assert parse_risk("Risk: MEDIUM\n") == "MEDIUM"


def test_parse_risk_bolded():
    assert parse_risk("**RISK** HIGH") == "HIGH"


def test_parse_risk_unknown():
    assert parse_risk("no risk stated here") == "UNKNOWN"


def test_enriched_from_structural_preserves_fields():
    src = _structural([_file()])
    result = EnrichedPlanResult.from_structural(src, "why", "LOW", "claude")
    assert result.task == src.task
    assert result.matched_files == src.matched_files
    assert result.rationale == "why"
    assert result.risk == "LOW"
    assert result.llm_provider == "claude"
