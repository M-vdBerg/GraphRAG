"""sentence-transformers embedding wrapper with CUDA support.

BGE asymmetric retrieval
────────────────────────
BGE English models (bge-large-en-v1.5, bge-base-en-v1.5, …) use asymmetric
embeddings for retrieval:
  - Document chunks are embedded as-is (no prefix).
  - Queries must be prefixed with the instruction string below.

BGE-M3 (multilingual, 100+ languages incl. German) does NOT use a query
prefix — both queries and passages are embedded identically.

The correct prefix behaviour is selected automatically in ``embed_query()``
based on the model name. Never call ``embed()`` with raw query strings.
"""

from __future__ import annotations

import logging

import torch
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

_BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Embedder:
    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        device: str = "cuda",
        batch_size: int = 16,
        precision: str = "fp16",
    ) -> None:
        dtype = torch.float16 if precision == "fp16" and device != "cpu" else torch.float32
        logger.info(
            "Loading embedding model '%s' on device '%s' (%s)",
            model_name, device, precision,
        )
        self._model = SentenceTransformer(
            model_name, device=device, model_kwargs={"torch_dtype": dtype}
        )
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
        """Embed a query string, applying a retrieval prefix where required."""
        prefixed = _bge_prefix(self._model_name, text)
        return self.embed([prefixed])[0]

    @property
    def dimensions(self) -> int:
        return self._model.get_sentence_embedding_dimension() or 0


def _bge_prefix(model_name: str, text: str) -> str:
    """Apply query prefix where the model requires it.

    - BGE English models (bge-large-en, bge-base-en, …): need the prefix.
    - BGE-M3 (multilingual): symmetric — no prefix for either queries or docs.
    - All other models: passed through unchanged.
    """
    name = model_name.lower()
    if "bge" in name and "m3" not in name:
        return _BGE_QUERY_PREFIX + text
    return text
