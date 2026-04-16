"""ONNX model and tokenizer cache manager with XDG-compliant paths."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Callable

import onnxruntime
import tokenizers
from huggingface_hub import hf_hub_download

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# HuggingFace repo identifier for the model we cache locally.
MODEL_NAME = "microsoft/unixcoder-base"


def _cache_base() -> Path:
    """Return the XDG-compliant root cache directory for code-palace.

    Respects XDG_CACHE_HOME when set; falls back to ~/.cache/code-palace
    so that the cache location is predictable on any POSIX system.
    """
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg) / "code-palace"
    return Path.home() / ".cache" / "code-palace"


# Resolved once at import time so callers share a stable path.
MODEL_CACHE_DIR: Path = _cache_base() / "models"

# ---------------------------------------------------------------------------
# ModelManager
# ---------------------------------------------------------------------------

# Both files must exist for the cache to be considered complete.
_REQUIRED_FILES: tuple[str, ...] = ("model.onnx", "tokenizer.json")


class ModelManager:
    """Manage the local ONNX model + tokenizer cache for UniXcoder.

    All I/O is scoped to MODEL_CACHE_DIR / "unixcoder-base" so that other
    model variants can live side-by-side without path collisions.

    Thread safety: directory creation uses exist_ok=True, making concurrent
    first-run calls safe without an additional lock.
    """

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    @staticmethod
    def model_dir() -> Path:
        """Return the directory that holds model.onnx and tokenizer.json."""
        return MODEL_CACHE_DIR / "unixcoder-base"

    # ------------------------------------------------------------------
    # Existence check
    # ------------------------------------------------------------------

    @staticmethod
    def model_exists() -> bool:
        """Return True only when BOTH model.onnx AND tokenizer.json are present.

        A partial download (one file missing) is treated as non-existent so
        that ensure_model() always re-completes the pair rather than silently
        leaving a broken cache.
        """
        d = ModelManager.model_dir()
        return all((d / f).is_file() for f in _REQUIRED_FILES)

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    @staticmethod
    def ensure_model(
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> Path:
        """Download model.onnx + tokenizer.json from HuggingFace Hub if absent.

        Uses huggingface_hub.hf_hub_download which handles HTTP resume,
        symlink caching, and authentication tokens automatically.  Each
        missing file is downloaded individually so a partial cache caused by
        an earlier interrupted run is always repaired.

        Args:
            progress_callback: Optional callable(downloaded_bytes, total_bytes).
                               Called once per file after it is written to disk.
                               Both arguments equal the final file size in bytes
                               because HF Hub does not expose streaming byte
                               counts through hf_hub_download.

        Returns:
            Path to the model directory containing both cached files.
        """
        dest = ModelManager.model_dir()
        # exist_ok=True keeps concurrent first-run calls safe.
        dest.mkdir(parents=True, exist_ok=True)

        for filename in _REQUIRED_FILES:
            target = dest / filename
            if target.is_file():
                # Already present — skip to avoid redundant network I/O.
                continue

            # hf_hub_download resolves to its own internal blob path; we copy
            # it into our layout so the path is always predictable regardless
            # of HF_HOME changes.
            local_path = hf_hub_download(
                repo_id=MODEL_NAME,
                filename=filename,
            )
            # copy2 preserves metadata and never breaks the HF blob cache.
            shutil.copy2(local_path, target)

            if progress_callback is not None:
                size = target.stat().st_size
                progress_callback(size, size)

        return dest

    # ------------------------------------------------------------------
    # Loaders
    # ------------------------------------------------------------------

    @staticmethod
    def load_tokenizer() -> tokenizers.Tokenizer:
        """Load and return the tokenizer from the local cache.

        Raises:
            Exception: propagated from tokenizers if tokenizer.json is absent
                       or malformed.
        """
        tokenizer_path = ModelManager.model_dir() / "tokenizer.json"
        return tokenizers.Tokenizer.from_file(str(tokenizer_path))

    @staticmethod
    def load_onnx_session() -> onnxruntime.InferenceSession:
        """Load and return an ONNX InferenceSession from the local cache.

        Raises:
            Exception: propagated from onnxruntime if model.onnx is absent
                       or incompatible with the installed runtime version.
        """
        model_path = ModelManager.model_dir() / "model.onnx"
        return onnxruntime.InferenceSession(str(model_path))
