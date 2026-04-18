"""Unit tests for palace.llm.explainer (T8)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from palace.core.exceptions import LLMError
from palace.llm.explainer import Explainer, ExplanationContext, _strip_fences
from palace.llm.prompts.explain import build_explain_message


def test_no_provider_structural_fallback():
    """Provider=None → structural fallback, no exception."""
    ctx = ExplanationContext(
        target="foo.py",
        files=[{"path": "foo.py", "language": "python", "file_id": 1}],
        symbols=[{"name": "bar", "kind": "function"}],
        concerns=[],
    )
    result = Explainer(None).explain(ctx)
    assert result.structural_only is True
    assert "foo.py" in result.text
    assert result.llm_provider == ""


def test_empty_context_no_llm_call():
    """FM-2: empty files/symbols → no LLM call."""
    provider = MagicMock()
    provider.name = "fake"
    ctx = ExplanationContext(target="empty/")

    result = Explainer(provider).explain(ctx)
    assert provider.complete.call_count == 0
    assert result.structural_only is True


def test_large_input_truncated():
    """FM-3: prompt bytes bounded by max_bytes."""
    symbols = [{"name": f"sym{i}", "kind": "function", "docstring": "x" * 1000} for i in range(1000)]
    msg = build_explain_message(
        "huge/", [{"path": "a.py", "language": "python"}], symbols, [], max_bytes=32_000
    )
    assert len(msg.encode("utf-8")) <= 32_500


def test_llm_error_falls_back():
    """LLM error → structural fallback with error note."""
    provider = MagicMock()
    provider.name = "fake"
    provider.complete.side_effect = LLMError("timeout")

    ctx = ExplanationContext(
        target="foo.py",
        files=[{"path": "foo.py", "language": "python", "file_id": 1}],
        symbols=[{"name": "bar", "kind": "function"}],
        concerns=[],
    )
    result = Explainer(provider).explain(ctx)
    assert result.structural_only is True
    assert "timeout" in result.text


def test_strip_fences_basic():
    assert _strip_fences("```\nfoo\n```") == "foo"


def test_strip_fences_markdown_lang():
    assert _strip_fences("```markdown\n# X\n```") == "# X"


def test_strip_fences_no_fences():
    assert _strip_fences("# X\nbody") == "# X\nbody"


def test_explainer_happy_path():
    provider = MagicMock()
    provider.name = "claude"
    provider.complete.return_value = "# Overview\nThis module handles auth."

    ctx = ExplanationContext(
        target="auth/",
        files=[{"path": "auth/login.py", "language": "python", "file_id": 1}],
        symbols=[{"name": "login", "kind": "function"}],
        concerns=[],
    )
    result = Explainer(provider).explain(ctx)
    assert result.structural_only is False
    assert "Overview" in result.text
    assert result.llm_provider == "claude"
