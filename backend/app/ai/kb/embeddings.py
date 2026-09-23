"""Embedding provider interface.

Business logic must depend only on EmbeddingProvider so the embedding
model can be swapped (e.g. a multilingual model for Hindi documents).
"""
from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod

import numpy as np

log = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    """Abstract text-embedding provider (sync; callers use to_thread)."""

    name: str = "base"

    @property
    def model_id(self) -> str:
        """Stable id of the embedding space (used to invalidate stale chunks)."""
        return self.name

    @property
    @abstractmethod
    def dim(self) -> int:
        """Embedding dimension."""

    @abstractmethod
    def embed(self, texts: list[str]) -> np.ndarray:
        """Return an (n, dim) float32 array of L2-normalized embeddings."""


class SentenceTransformerEmbeddings(EmbeddingProvider):
    """Local sentence-transformers embeddings (open source, CPU-friendly).

    Multilingual by default so English, Hindi (Devanagari) and Hinglish
    documents all retrieve well. The model downloads once from Hugging
    Face (~420 MB for paraphrase-multilingual-MiniLM-L12-v2) and is
    cached under HF_HOME / ~/.cache.
    """

    name = "sentence-transformers"

    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2") -> None:
        self._model_name = model_name
        self._model = None
        self._dim: int | None = None

    @property
    def model_id(self) -> str:
        return self._model_name

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "sentence-transformers is not installed "
                    "(pip install sentence-transformers)."
                ) from exc
            log.info("Loading embedding model '%s' ...", self._model_name)
            self._model = SentenceTransformer(self._model_name)
            get_dim = getattr(self._model, "get_embedding_dimension", None) or getattr(
                self._model, "get_sentence_embedding_dimension"
            )
            self._dim = int(get_dim())
            log.info("Embedding model ready (dim=%d).", self._dim)
        return self._model

    @property
    def dim(self) -> int:
        self._load()
        assert self._dim is not None
        return self._dim

    def embed(self, texts: list[str]) -> np.ndarray:
        model = self._load()
        vecs = model.encode(
            [t or "" for t in texts],
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vecs, dtype=np.float32)


class HashEmbeddings(EmbeddingProvider):
    """Deterministic hashing-trick embeddings (tests / offline fallback).

    Not semantic — only for unit tests and environments without models.
    """

    name = "hash"

    def __init__(self, dim: int = 128) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self._dim), dtype=np.float32)
        for i, text in enumerate(texts):
            for token in (text or "").lower().split():
                h = int(hashlib.md5(token.encode()).hexdigest(), 16)
                out[i, h % self._dim] += 1.0
            norm = np.linalg.norm(out[i])
            if norm > 0:
                out[i] /= norm
        return out


_provider: EmbeddingProvider | None = None


def get_embedding_provider(model_name: str | None = None) -> EmbeddingProvider:
    """Process-wide singleton embedding provider (lazy model load)."""
    global _provider
    if _provider is None:
        from app.core.config import settings

        name = model_name or getattr(
            settings, "KB_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"
        )
        _provider = SentenceTransformerEmbeddings(name)
    return _provider


def set_embedding_provider(provider: EmbeddingProvider | None) -> None:
    """Override the singleton (used by tests)."""
    global _provider
    _provider = provider
