"""Unit tests for the Embedder — uses a tiny local model to avoid GPU dependency."""

from __future__ import annotations

import pytest

from graphrag.embeddings.embedder import Embedder, _bge_prefix


class TestBGEPrefix:
    def test_bge_model_gets_prefix(self) -> None:
        result = _bge_prefix("BAAI/bge-large-en-v1.5", "hello world")
        assert result.startswith("Represent this sentence")
        assert "hello world" in result

    def test_non_bge_model_no_prefix(self) -> None:
        result = _bge_prefix("intfloat/e5-large-v2", "hello world")
        assert result == "hello world"

    def test_bge_case_insensitive(self) -> None:
        result = _bge_prefix("BAAI/BGE-small-en", "test")
        assert result.startswith("Represent")


class TestEmbedder:
    """Integration-style tests — requires sentence-transformers installed.

    Uses a small model (all-MiniLM-L6-v2) so tests run quickly on CPU.
    Override EMBEDDING_MODEL=BAAI/bge-large-en-v1.5 in CI with GPU runners.
    """

    @pytest.fixture(scope="class")
    def embedder(self) -> Embedder:
        return Embedder(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            device="cpu",
            batch_size=8,
        )

    def test_embed_returns_list_of_floats(self, embedder: Embedder) -> None:
        vecs = embedder.embed(["hello world"])
        assert len(vecs) == 1
        assert isinstance(vecs[0], list)
        assert all(isinstance(v, float) for v in vecs[0])

    def test_embed_batch(self, embedder: Embedder) -> None:
        texts = ["foo", "bar", "baz"]
        vecs = embedder.embed(texts)
        assert len(vecs) == 3
        assert all(len(v) == embedder.dimensions for v in vecs)

    def test_embed_empty_list(self, embedder: Embedder) -> None:
        assert embedder.embed([]) == []

    def test_embed_query_returns_single_vector(self, embedder: Embedder) -> None:
        vec = embedder.embed_query("what is GraphRAG?")
        assert isinstance(vec, list)
        assert len(vec) == embedder.dimensions

    def test_normalized_embeddings(self, embedder: Embedder) -> None:
        import math
        vec = embedder.embed(["normalize me"])[0]
        norm = math.sqrt(sum(v * v for v in vec))
        assert abs(norm - 1.0) < 1e-4
