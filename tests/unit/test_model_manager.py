"""T_9 gate tests — ONNX ModelManager cache path and existence checks."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

import palace.semantic.model_manager as mm_module
from palace.semantic.model_manager import ModelManager


# ---------------------------------------------------------------------------
# T_9.1 — Cache directory construction
# ---------------------------------------------------------------------------


class TestCacheDir:
    """T_9.1 — _cache_base() must produce XDG-compliant paths."""

    def test_xdg_set(self, tmp_path: Path) -> None:
        """T_9.1: with XDG_CACHE_HOME set the cache root is inside it."""
        with patch.dict("os.environ", {"XDG_CACHE_HOME": str(tmp_path)}):
            result = mm_module._cache_base()
        # The returned path must be rooted at the overridden XDG directory.
        assert str(result).startswith(str(tmp_path))
        assert result == tmp_path / "code-palace"

    def test_xdg_fallback(self, tmp_path: Path) -> None:
        """T_9.1: without XDG_CACHE_HOME the path falls back to ~/.cache/code-palace."""
        env_without_xdg = {
            k: v for k, v in __import__("os").environ.items()
            if k != "XDG_CACHE_HOME"
        }
        with patch.dict("os.environ", env_without_xdg, clear=True):
            result = mm_module._cache_base()
        expected = Path.home() / ".cache" / "code-palace"
        assert result == expected


# ---------------------------------------------------------------------------
# T_9.2 — model_exists() partial-download detection
# ---------------------------------------------------------------------------


class TestModelExists:
    """T_9.2 — model_exists() must require both files to be present."""

    def test_empty_dir(self, tmp_path: Path) -> None:
        """T_9.2: model_exists() returns False when the cache directory is empty."""
        fake_model_dir = tmp_path / "unixcoder-base"
        fake_model_dir.mkdir()

        with patch.object(ModelManager, "model_dir", return_value=fake_model_dir):
            assert ModelManager.model_exists() is False

    def test_both_files(self, tmp_path: Path) -> None:
        """T_9.2: model_exists() returns True when both required files are present."""
        fake_model_dir = tmp_path / "unixcoder-base"
        fake_model_dir.mkdir()
        (fake_model_dir / "model.onnx").write_bytes(b"fake-onnx")
        (fake_model_dir / "tokenizer.json").write_text("{}")

        with patch.object(ModelManager, "model_dir", return_value=fake_model_dir):
            assert ModelManager.model_exists() is True

    def test_partial_onnx_only(self, tmp_path: Path) -> None:
        """T_9.2: model_exists() returns False when only model.onnx is present."""
        fake_model_dir = tmp_path / "unixcoder-base"
        fake_model_dir.mkdir()
        (fake_model_dir / "model.onnx").write_bytes(b"fake-onnx")
        # tokenizer.json intentionally absent

        with patch.object(ModelManager, "model_dir", return_value=fake_model_dir):
            assert ModelManager.model_exists() is False

    def test_partial_tokenizer_only(self, tmp_path: Path) -> None:
        """T_9.2: model_exists() returns False when only tokenizer.json is present."""
        fake_model_dir = tmp_path / "unixcoder-base"
        fake_model_dir.mkdir()
        (fake_model_dir / "tokenizer.json").write_text("{}")
        # model.onnx intentionally absent

        with patch.object(ModelManager, "model_dir", return_value=fake_model_dir):
            assert ModelManager.model_exists() is False
