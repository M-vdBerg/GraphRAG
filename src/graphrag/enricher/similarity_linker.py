"""Embedding-based SIMILAR_TO edge creation using pgvector.

Uses a LATERAL join against the IVFFlat index to find the top-K most similar
chunks (from different documents) for each chunk in the corpus.
This is O(N × K × log N) — far cheaper than the naive O(N²) cross join.

Edges are created in both directions and are idempotent (MERGE in AGE).
"""

from __future__ import annotations

import logging

import asyncpg

from graphrag.graph.age_client import AGEClient

logger = logging.getLogger(__name__)


class SimilarityLinker:
    def __init__(self, age: AGEClient, threshold: float, max_per_chunk: int) -> None:
        self._age = age
        self._threshold = threshold
        self._max_per_chunk = max_per_chunk

    async def run(self, pool: asyncpg.Pool) -> int:  # type: ignore[type-arg]
        """Compute and persist SIMILAR_TO edges across the entire corpus.

        Returns the number of unique chunk pairs linked.
        """
        pairs = await self._find_similar_pairs(pool)
        if not pairs:
            logger.info("No chunk pairs above similarity threshold %.2f", self._threshold)
            return 0

        created = 0
        async with pool.acquire() as conn:
            await conn.execute("LOAD 'age'")
            await conn.execute("SET search_path = ag_catalog, graphrag, public")
            async with conn.transaction():
                for chunk_a, chunk_b, score in pairs:
                    await self._age.create_similar_to_edge(conn, chunk_a, chunk_b, score)
                    created += 1

        logger.info("Created/updated %d SIMILAR_TO edge pairs (threshold=%.2f)", created, self._threshold)
        return created

    async def _find_similar_pairs(
        self,
        pool: asyncpg.Pool,  # type: ignore[type-arg]
    ) -> list[tuple[str, str, float]]:
        """Return deduplicated (chunk_a, chunk_b, score) tuples above threshold.

        Uses pgvector LATERAL join so the IVFFlat index is used for each probe.
        We canonicalise pairs as (min_id, max_id) to avoid processing (a,b)
        and (b,a) separately — the AGE method creates both directions.
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT
                    LEAST(a.chunk_id, b.chunk_id)    AS chunk_a,
                    GREATEST(a.chunk_id, b.chunk_id) AS chunk_b,
                    1 - (a.embedding <=> b.embedding) AS score
                FROM graphrag.chunks a
                CROSS JOIN LATERAL (
                    SELECT c.chunk_id, c.doc_id
                    FROM graphrag.chunks c
                    WHERE c.doc_id != a.doc_id
                    ORDER BY a.embedding <=> c.embedding
                    LIMIT $1
                ) b
                WHERE 1 - (a.embedding <=> b.embedding) >= $2
                """,
                self._max_per_chunk,
                self._threshold,
            )
        return [(r["chunk_a"], r["chunk_b"], float(r["score"])) for r in rows]
