"""Embedding engine — produces 768-dimensional vectors from text using ONNX Runtime."""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from palace.core.logging import get_logger

if TYPE_CHECKING:
    import onnxruntime
    import tokenizers

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# UniXcoder maximum context window in tokens.
# Inputs longer than this are silently truncated before inference.
_MAX_TOKENS: int = 512

# Output dimensionality produced by UniXcoder's [CLS] token.
# Every method in this module guarantees vectors of exactly this length.
_EMBED_DIM: int = 768


# ---------------------------------------------------------------------------
# EmbeddingEngine
# ---------------------------------------------------------------------------


class EmbeddingEngine:
    """Produces 768-dimensional text embeddings via a locally-cached ONNX model.

    Lifecycle: instantiate → first call to embed() or embed_batch() triggers
    lazy model load → subsequent calls reuse the loaded session.
    """

    def __init__(self, model_dir: Path | None = None) -> None:
        # Defer model_dir resolution to first use so ModelManager is only
        # imported when a real engine is actually constructed.
        self._model_dir: Path | None = model_dir
        # Lazy-loaded state — None until _ensure_loaded() is called.
        self._tokenizer: tokenizers.Tokenizer | None = None
        self._session: onnxruntime.InferenceSession | None = None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        """Load tokenizer and ONNX session on first use.

        Separated from __init__ so the heavy I/O (disk reads, ONNX graph
        compilation) is deferred until an embedding is actually requested,
        keeping import time low.
        """
        if self._tokenizer is not None and self._session is not None:
            return

        # Resolve model directory lazily to avoid importing ModelManager at
        # module load time — ModelManager itself imports onnxruntime which can
        # be slow on first import.
        if self._model_dir is None:
            from palace.semantic.model_manager import ModelManager  # noqa: E402

            self._model_dir = ModelManager.model_dir()

        import onnxruntime  # noqa: E402
        import tokenizers as tok  # noqa: E402

        self._tokenizer = tok.Tokenizer.from_file(str(self._model_dir / "tokenizer.json"))
        self._session = onnxruntime.InferenceSession(str(self._model_dir / "model.onnx"))

    @staticmethod
    def _zero_vector() -> list[float]:
        """Return a 768-dimensional zero vector.

        Used for empty-string inputs so callers always receive a valid
        fixed-length vector rather than an error or a shorter result.
        """
        return [0.0] * _EMBED_DIM

    def _tokenize(self, text: str) -> tuple[list[int], list[int]]:
        """Tokenize text and return (input_ids, attention_mask) truncated to _MAX_TOKENS.

        Truncating here — not in the ONNX graph — keeps the padding logic
        simple and avoids potential out-of-bounds errors in the model.
        """
        assert self._tokenizer is not None  # guaranteed by _ensure_loaded()
        encoding = self._tokenizer.encode(text)
        if len(encoding.ids) > _MAX_TOKENS:
            logger.debug(
                "Input truncated from %d to %d tokens",
                len(encoding.ids),
                _MAX_TOKENS,
            )
        input_ids: list[int] = encoding.ids[:_MAX_TOKENS]
        attention_mask: list[int] = [1] * len(input_ids)
        return input_ids, attention_mask

    @staticmethod
    def _pad_to_length(
        input_ids: list[int],
        attention_mask: list[int],
        length: int,
    ) -> tuple[list[int], list[int]]:
        """Pad input_ids and attention_mask to a fixed sequence length.

        Padding token id 1 (UniXcoder convention) fills input_ids; 0 fills
        attention_mask so the model attends only to real tokens.
        """
        pad_len = length - len(input_ids)
        padded_ids = input_ids + [1] * pad_len
        padded_mask = attention_mask + [0] * pad_len
        return padded_ids, padded_mask

    def _run_inference(self, input_ids: list[int], attention_mask: list[int]) -> list[float]:
        """Run ONNX inference and extract the [CLS] token embedding.

        The [CLS] token is always position 0 of the last hidden state, and
        carries a summary representation of the full input sequence.
        """
        assert self._session is not None  # guaranteed by _ensure_loaded()

        ids_array = np.array([input_ids], dtype=np.int64)
        mask_array = np.array([attention_mask], dtype=np.int64)

        outputs = self._session.run(
            None,
            {"input_ids": ids_array, "attention_mask": mask_array},
        )
        # outputs[0] shape: (batch=1, seq_len, hidden=768)
        # Index [0, 0, :] extracts the [CLS] token for the single example.
        cls_vector: list[float] = outputs[0][0][0].tolist()
        return cls_vector

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed(self, text: str) -> list[float]:
        """Embed a single text string and return a 768-dimensional vector.

        Empty input returns a zero vector rather than raising so callers
        can embed arbitrary untrusted text without wrapping in try/except.
        """
        if not text:
            return self._zero_vector()

        self._ensure_loaded()
        input_ids, attention_mask = self._tokenize(text)
        if not input_ids:
            # Tokenizer produced no tokens (e.g. whitespace-only input).
            return self._zero_vector()

        padded_ids, padded_mask = self._pad_to_length(input_ids, attention_mask, _MAX_TOKENS)
        return self._run_inference(padded_ids, padded_mask)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts and return one 768-dim vector per input.

        Each text is embedded independently.  Batching at the ONNX level is
        a future optimisation; correctness takes priority here.
        """
        return [self.embed(text) for text in texts]


# ---------------------------------------------------------------------------
# MockEmbeddingEngine
# ---------------------------------------------------------------------------


class MockEmbeddingEngine:
    """Deterministic 768-dimensional embedding engine backed by SHA-256.

    Intended for tests and offline development only — no ONNX model or GPU
    required.  The same input always produces the same output vector, which
    makes assertions stable across runs and environments.
    """

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_to_vector(text: str) -> list[float]:
        """Derive a deterministic 768-dim float vector from the SHA-256 of text.

        SHA-256 produces 32 bytes; repeating and slicing to 768 bytes then
        normalising each byte to [0.0, 1.0] gives a stable, unique-per-input
        vector without any model dependency.
        """
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        # 32 bytes repeated 24 times = 768 bytes exactly.
        repeated = (digest * 24)[:_EMBED_DIM]
        # Unpack as 768 unsigned bytes and normalise to float in [0.0, 1.0].
        raw: tuple[int, ...] = struct.unpack(f"{_EMBED_DIM}B", repeated)
        return [b / 255.0 for b in raw]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed(self, text: str) -> list[float]:
        """Return a deterministic 768-dim vector based on the SHA-256 of text.

        Empty string maps to the hash of an empty byte sequence, which is a
        well-defined non-zero vector, ensuring callers always receive a valid
        768-dimensional result regardless of input.
        """
        return self._hash_to_vector(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts by calling embed() for each.

        Returns an empty list when texts is empty, matching the contract of
        EmbeddingEngine.embed_batch so the two classes are interchangeable.
        """
        return [self.embed(text) for text in texts]
