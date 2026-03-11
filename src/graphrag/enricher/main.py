"""Enricher entry point.

Runs two enrichment passes over the indexed corpus:

  1. SIMILAR_TO edges  — pure embedding cosine similarity via pgvector (no LLM).
  2. Entity extraction — LLM call per unprocessed chunk, MENTIONS edges in AGE.

Incremental: only chunks whose content has changed since the last run (or that
have never been processed by the configured model) are sent to the LLM.

Usage (inside the watcher container):
  docker compose exec watcher python -m graphrag.enricher

Or locally (requires DB reachable on localhost):
  POSTGRES_HOST=localhost python -m graphrag.enricher

Override model / endpoint via env vars:
  ENRICHER_MODEL=mistral/mistral-small-24b \
  ENRICHER_BASE_URL=http://localhost:4000/v1 \
  python -m graphrag.enricher
"""

from __future__ import annotations

import asyncio
import hashlib
import logging

import asyncpg

from graphrag.config import settings
from graphrag.db.connection import create_pool
from graphrag.enricher.entity_extractor import EntityExtractor, ExtractionResult
from graphrag.enricher.similarity_linker import SimilarityLinker
from graphrag.graph.age_client import AGEClient
from graphrag.graph.schema import EntityNode

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("graphrag.enricher")


# ─── Entity helpers ───────────────────────────────────────────────────────────

def _entity_id(normalized: str, etype: str) -> str:
    return hashlib.sha256(f"{normalized}|{etype}".encode()).hexdigest()


async def _persist_extraction(
    pool: asyncpg.Pool,  # type: ignore[type-arg]
    age: AGEClient,
    chunk_id: str,
    content: str,
    result: ExtractionResult,
    model: str,
) -> None:
    """Write entities + enrichment_log row for one chunk (single transaction)."""
    content_hash = hashlib.sha256(content.encode()).hexdigest()

    async with pool.acquire() as conn:
        await conn.execute("LOAD 'age'")
        await conn.execute("SET search_path = ag_catalog, graphrag, public")
        async with conn.transaction():
            # Remove stale MENTIONS edges before re-writing
            await age.delete_mentions_for_chunk(conn, chunk_id)

            for ent in result.entities:
                eid = _entity_id(ent["normalized"], ent["type"])
                node = EntityNode(
                    entity_id=eid,
                    name=ent["name"],
                    type=ent["type"],
                    normalized=ent["normalized"],
                )

                # Relational upsert
                await conn.execute(
                    """
                    INSERT INTO graphrag.entities (entity_id, name, type, normalized)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (entity_id) DO NOTHING
                    """,
                    eid, ent["name"], ent["type"], ent["normalized"],
                )
                await conn.execute(
                    """
                    INSERT INTO graphrag.chunk_entities (chunk_id, entity_id, model)
                    VALUES ($1, $2, $3)
                    ON CONFLICT DO NOTHING
                    """,
                    chunk_id, eid, model,
                )

                # AGE vertex + edge
                await age.upsert_entity(conn, node)
                await age.create_mentions_edge(conn, chunk_id, eid)

            # Mark chunk as enriched
            await conn.execute(
                """
                INSERT INTO graphrag.enrichment_log (chunk_id, model, content_hash, enriched_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (chunk_id, model) DO UPDATE
                    SET content_hash = EXCLUDED.content_hash,
                        enriched_at  = NOW()
                """,
                chunk_id, model, content_hash,
            )


# ─── Main enrichment loop ─────────────────────────────────────────────────────

async def _fetch_pending_chunks(
    pool: asyncpg.Pool,  # type: ignore[type-arg]
    model: str,
) -> list[dict]:
    """Return chunks not yet enriched (or whose content changed) for this model."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT c.chunk_id, c.doc_id, c.content, c.heading, c.position
            FROM graphrag.chunks c
            LEFT JOIN graphrag.enrichment_log e
                   ON e.chunk_id = c.chunk_id AND e.model = $1
            WHERE e.chunk_id IS NULL
               OR e.content_hash != encode(sha256(c.content::bytea), 'hex')
            ORDER BY c.doc_id, c.position
            """,
            model,
        )
    return [dict(r) for r in rows]


async def run_entity_extraction(
    pool: asyncpg.Pool,  # type: ignore[type-arg]
    age: AGEClient,
    extractor: EntityExtractor,
    model: str,
    concurrency: int,
) -> None:
    chunks = await _fetch_pending_chunks(pool, model)
    if not chunks:
        logger.info("Entity extraction: nothing to do (all chunks up to date)")
        return

    logger.info("Entity extraction: %d chunk(s) to process with model '%s'", len(chunks), model)

    sem = asyncio.Semaphore(concurrency)

    async def process_one(chunk: dict) -> None:
        async with sem:
            result = await extractor.extract(chunk["content"])
            await _persist_extraction(pool, age, chunk["chunk_id"], chunk["content"], result, model)
            logger.debug(
                "  chunk %s (%s pos %d): %d entities",
                chunk["chunk_id"][:8],
                chunk.get("heading") or "<preamble>",
                chunk["position"],
                len(result.entities),
            )

    await asyncio.gather(*[process_one(c) for c in chunks])
    logger.info("Entity extraction complete")


async def main() -> None:
    logger.info("GraphRAG Enricher starting")
    logger.info("  model      : %s", settings.enricher_model)
    logger.info("  base_url   : %s", settings.enricher_base_url)
    logger.info("  sim thresh : %.2f  max/chunk: %d", settings.similar_to_threshold, settings.similar_to_max_per_chunk)

    pool = await create_pool()
    age = AGEClient()
    extractor = EntityExtractor(
        base_url=settings.enricher_base_url,
        api_key=settings.enricher_api_key,
        model=settings.enricher_model,
    )
    linker = SimilarityLinker(
        age=age,
        threshold=settings.similar_to_threshold,
        max_per_chunk=settings.similar_to_max_per_chunk,
    )

    # Pass 1: embedding-based SIMILAR_TO (no LLM, fast)
    logger.info("Pass 1: computing SIMILAR_TO edges …")
    n_pairs = await linker.run(pool)
    logger.info("Pass 1 done: %d pairs linked", n_pairs)

    # Pass 2: LLM entity extraction
    logger.info("Pass 2: entity extraction …")
    await run_entity_extraction(
        pool=pool,
        age=age,
        extractor=extractor,
        model=settings.enricher_model,
        concurrency=settings.enricher_concurrency,
    )

    await pool.close()
    logger.info("Enricher finished")


if __name__ == "__main__":
    asyncio.run(main())
