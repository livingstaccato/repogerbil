# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Embedding model wrapper — generates vector representations of text."""

from __future__ import annotations

from typing import Protocol, cast


class Embedder(Protocol):  # pragma: no cover — Protocol class, no runtime code
    """Protocol for embedding models."""

    def embed(self, text: str) -> list[float]: ...
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class SentenceTransformerEmbedder:  # pragma: no cover — requires sentence-transformers ML model
    """Embedder using sentence-transformers (local, no API key needed)."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            msg = "sentence-transformers not installed. Run: pip install repogerbil[vectordb]"
            raise ImportError(msg) from e
        self._model = SentenceTransformer(model_name)

    def embed(self, text: str) -> list[float]:
        """Embed a single text string."""
        return cast(list[float], self._model.encode(text).tolist())

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of text strings."""
        return cast(list[list[float]], self._model.encode(texts).tolist())


class SimpleHashEmbedder:
    """Deterministic hash-based embedder for testing (no ML model needed).

    Produces consistent but not semantically meaningful embeddings.
    """

    def __init__(self, dimensions: int = 384) -> None:
        self._dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        """Generate a deterministic embedding from text hash."""
        import hashlib

        h = hashlib.sha256(text.encode()).hexdigest()
        values: list[float] = []
        for i in range(self._dimensions):
            byte_idx = i % 32
            values.append((int(h[byte_idx * 2 : byte_idx * 2 + 2], 16) - 128) / 128.0)
        return values

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch using hash-based embedding."""
        return [self.embed(t) for t in texts]
