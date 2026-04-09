# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for embedding models."""

from repogerbil.core.embeddings import SimpleHashEmbedder


class TestSimpleHashEmbedder:
    def test_default_dimensions_is_384(self) -> None:
        e = SimpleHashEmbedder()
        assert e._dimensions == 384

    def test_embed_returns_list(self) -> None:
        e = SimpleHashEmbedder()
        result = e.embed("hello world")
        assert isinstance(result, list)
        assert len(result) == 384

    def test_embed_deterministic(self) -> None:
        e = SimpleHashEmbedder()
        a = e.embed("same text")
        b = e.embed("same text")
        assert a == b

    def test_different_text_different_embedding(self) -> None:
        e = SimpleHashEmbedder()
        a = e.embed("hello")
        b = e.embed("world")
        assert a != b

    def test_custom_dimensions(self) -> None:
        e = SimpleHashEmbedder(dimensions=128)
        result = e.embed("test")
        assert len(result) == 128

    def test_embed_batch(self) -> None:
        e = SimpleHashEmbedder()
        results = e.embed_batch(["hello", "world"])
        assert len(results) == 2
        assert all(len(r) == 384 for r in results)

    def test_values_in_range(self) -> None:
        e = SimpleHashEmbedder()
        result = e.embed("test")
        assert all(-1.0 <= v <= 1.0 for v in result)

    def test_embed_has_stable_prefix_values(self) -> None:
        e = SimpleHashEmbedder(dimensions=4)
        assert e.embed("hello") == [-0.65625, 0.890625, -0.3984375, 0.453125]
