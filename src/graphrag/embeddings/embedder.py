"""sentence-transformers embedding wrapper with CUDA support.

BGE asymmetric retrieval
────────────────────────
BAAI/bge-large-en-v1.5 uses *asymmetric* embeddings for retrieval:
  - Document chunks are embedded as-is (no prefix).
  - Queries must be prefixed with the instruction string below.

Skipping the query prefix significantly degrades recall. The prefix is applied
automatically in ``embed_query()``. Never use ``embed()`` for query strings.
"""

from __future__ import annotations

import logging

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

_BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Embedder:
    def __init__(
        self,
        model_name: str = "BAAI/bge-large-en-v1.5",
        device: str = "cuda",
        batch_size: int = 32,
    ) -> None:
        logger.info("Loading embedding model '%s' on device '%s'", model_name, device)
        self._model = SentenceTransformer(model_name, device=device)
        self._batch_size = batch_size
        self._model_name = model_name

    # ── Public API ────────────────────────────────────────────────────────────

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of document-side texts (chunks).

        Embeddings are L2-normalised so cosine similarity reduces to dot product.
        """
        if not texts:
            return []
        vectors = self._model.encode(
            texts,
            batch_size=self._batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [v.tolist() for v in vectors]

    def embed_query(self, text: str) -> list[float]:
        """Embed a query string, applying the BGE retrieval prefix."""
        prefixed = _bge_prefix(self._model_name, text)
        return self.embed([prefixed])[0]

    @property
    def dimensions(self) -> int:
        return self._model.get_sentence_embedding_dimension() or 0


def _bge_prefix(model_name: str, text: str) -> str:
    """Apply query prefix for BGE-family models; pass through for others."""
    if "bge" in model_name.lower():
        return _BGE_QUERY_PREFIX + text
    return text
