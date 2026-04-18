"""Unit tests for palace.llm.onboarder (T9)."""

from __future__ import annotations

from unittest.mock import MagicMock

from palace.core.exceptions import LLMError
from palace.llm.onboarder import Onboarder, OnboardContext
from palace.llm.prompts.onboard import build_onboard_message


def test_no_domains_graceful_hint():
    """FM-1: no domains → fallback mentions re-indexing."""
    ctx = OnboardContext(root="/p", file_count=10, symbol_count=100, domains=[])
    result = Onboarder(None).generate(ctx)
    assert result.structural_only is True
    assert "domain clusters" in result.text or "domain" in result.text


def test_prompt_per_domain_capped():
    """FM-3: per-domain sample capped at 10 files."""
    domains = [
        {"name": "d1", "sample_files": [f"f{i}.py" for i in range(500)]}
    ]
    msg = build_onboard_message(
        "/p", 500, 1000, domains, [], [], [], max_per_domain=10
    )
    # Each sample file appears as `filename` wrapped in backticks
    sample_count = msg.count("`f")
    assert sample_count == 10


def test_fenced_markdown_stripped():
    """FM-4: leading ```markdown fence is stripped."""
    provider = MagicMock()
    provider.name = "fake"
    provider.complete.return_value = "```markdown\n# X\n```"

    ctx = OnboardContext(
        root="/p", file_count=1, symbol_count=1, domains=[{"name": "d1"}]
    )
    result = Onboarder(provider).generate(ctx)
    assert result.text.startswith("# X")
    assert "```" not in result.text


def test_llm_error_falls_back():
    provider = MagicMock()
    provider.name = "fake"
    provider.complete.side_effect = LLMError("boom")

    ctx = OnboardContext(root="/p", file_count=1, symbol_count=1, domains=[{"name": "d"}])
    result = Onboarder(provider).generate(ctx)
    assert result.structural_only is True
    assert "boom" in result.text


def test_happy_path():
    provider = MagicMock()
    provider.name = "claude"
    provider.complete.return_value = "## Codebase Tour\nAll is well."

    ctx = OnboardContext(
        root="/p", file_count=10, symbol_count=100, domains=[{"name": "core"}]
    )
    result = Onboarder(provider).generate(ctx)
    assert result.structural_only is False
    assert "Codebase Tour" in result.text
    assert result.llm_provider == "claude"


def test_structural_includes_entry_points():
    ctx = OnboardContext(
        root="/p",
        file_count=10,
        symbol_count=100,
        domains=[{"name": "d1"}],
        entry_points=[{"path": "main.py", "dependent_count": 5}],
    )
    result = Onboarder(None).generate(ctx)
    assert "main.py" in result.text
