"""Apache AGE Cypher operations for the GraphRAG graph.

AGE parameter-passing notes
────────────────────────────
``ag_catalog.cypher()`` accepts a third argument of type ``agtype`` (a JSON-
compatible superset). We pass parameters as a JSON string cast to ``::agtype``
and reference them inside Cypher as ``$param_name``.

asyncpg cannot bind values *inside* the Cypher string — all dynamic user-
supplied values must go through the agtype parameters dict. Only structural
identifiers (label names, graph name) are interpolated as f-string literals,
and those values never come from user input.

The connection must have already executed ``LOAD 'age'`` and
``SET search_path = ag_catalog, ...`` — the pool's ``init`` callback in
``db/connection.py`` handles this.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import asyncpg

from graphrag.graph.schema import ChunkNode, DocumentNode

logger = logging.getLogger(__name__)

GRAPH_NAME = "graphrag"


class AGEClient:
    """Thin wrapper around AGE Cypher queries."""

    # ── Internal helper ───────────────────────────────────────────────────────

    async def _cypher(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        query: str,
        params: dict | None = None,
        return_columns: list[str] | None = None,
    ) -> list[asyncpg.Record]:  # type: ignore[type-arg]
        """Execute a Cypher query via ag_catalog.cypher().

        ``return_columns`` must match the Cypher RETURN clause aliases.
        Each column is typed as ``agtype`` in the SQL wrapper.
        """
        params_str = json.dumps(params or {})
        if return_columns:
            cols_sql = ", ".join(f"{c} agtype" for c in return_columns)
        else:
            cols_sql = "result agtype"

        sql = f"""
            SELECT * FROM ag_catalog.cypher(
                '{GRAPH_NAME}',
                $$ {query} $$,
                $1::agtype
            ) AS ({cols_sql})
        """
        try:
            return await conn.fetch(sql, params_str)
        except Exception:
            logger.exception("AGE Cypher error.\nQuery: %s\nParams: %s", query, params_str)
            raise

    # ── Document vertices ─────────────────────────────────────────────────────

    async def upsert_document(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        doc: DocumentNode,
    ) -> None:
        updated_at = doc.updated_at or datetime.now(timezone.utc).isoformat()
        await self._cypher(
            conn,
            """
            MERGE (d:Document {doc_id: $doc_id})
            SET d.file_path  = $file_path,
                d.file_name  = $file_name,
                d.title      = $title,
                d.updated_at = $updated_at
            """,
            {
                "doc_id": doc.doc_id,
                "file_path": doc.file_path,
                "file_name": doc.file_name,
                "title": doc.title or "",
                "updated_at": updated_at,
            },
        )

    async def delete_document(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        doc_id: str,
    ) -> None:
        """Remove Document vertex, all its Chunk vertices, and all edges."""
        await self._cypher(
            conn,
            """
            MATCH (d:Document {doc_id: $doc_id})
            OPTIONAL MATCH (d)-[:HAS_CHUNK]->(c:Chunk)
            DETACH DELETE d, c
            """,
            {"doc_id": doc_id},
        )

    # ── Chunk vertices ────────────────────────────────────────────────────────

    async def upsert_chunk(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        chunk: ChunkNode,
    ) -> None:
        await self._cypher(
            conn,
            """
            MERGE (c:Chunk {chunk_id: $chunk_id})
            SET c.doc_id      = $doc_id,
                c.heading     = $heading,
                c.position    = $position,
                c.content     = $content,
                c.token_count = $token_count
            """,
            {
                "chunk_id": chunk.chunk_id,
                "doc_id": chunk.doc_id,
                "heading": chunk.heading or "",
                "position": chunk.position,
                "content": chunk.content,
                "token_count": chunk.token_count or 0,
            },
        )

    async def delete_chunks_for_doc(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        doc_id: str,
    ) -> None:
        await self._cypher(
            conn,
            """
            MATCH (c:Chunk {doc_id: $doc_id})
            DETACH DELETE c
            """,
            {"doc_id": doc_id},
        )

    # ── Edges ─────────────────────────────────────────────────────────────────

    async def create_has_chunk_edge(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        doc_id: str,
        chunk_id: str,
        position: int,
    ) -> None:
        await self._cypher(
            conn,
            """
            MATCH (d:Document {doc_id: $doc_id}), (c:Chunk {chunk_id: $chunk_id})
            MERGE (d)-[r:HAS_CHUNK {position: $position}]->(c)
            """,
            {"doc_id": doc_id, "chunk_id": chunk_id, "position": position},
        )

    async def create_next_chunk_edges(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        chunk_ids_ordered: list[str],
    ) -> None:
        """Create NEXT_CHUNK edges between consecutive chunks in order."""
        for i in range(len(chunk_ids_ordered) - 1):
            await self._cypher(
                conn,
                """
                MATCH (a:Chunk {chunk_id: $src}), (b:Chunk {chunk_id: $tgt})
                MERGE (a)-[:NEXT_CHUNK]->(b)
                """,
                {"src": chunk_ids_ordered[i], "tgt": chunk_ids_ordered[i + 1]},
            )

    async def create_links_to_edge(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        src_doc_id: str,
        tgt_doc_id: str,
        anchor: str,
        href: str,
    ) -> None:
        await self._cypher(
            conn,
            """
            MATCH (src:Document {doc_id: $src_doc_id}), (tgt:Document {doc_id: $tgt_doc_id})
            MERGE (src)-[r:LINKS_TO {href: $href}]->(tgt)
            SET r.anchor = $anchor
            """,
            {
                "src_doc_id": src_doc_id,
                "tgt_doc_id": tgt_doc_id,
                "anchor": anchor,
                "href": href,
            },
        )

    # ── Traversal queries ─────────────────────────────────────────────────────

    async def get_related_documents(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        doc_id: str,
        depth: int = 2,
        direction: str = "both",
    ) -> list[dict]:
        """Return documents reachable from ``doc_id`` via LINKS_TO edges.

        ``direction`` controls traversal direction:
          - "outgoing": only follow outgoing edges
          - "incoming": only follow incoming edges
          - "both": follow edges in either direction
        """
        if direction == "outgoing":
            pattern = "(src:Document {doc_id: $doc_id})-[:LINKS_TO*1..$depth]->(rel:Document)"
        elif direction == "incoming":
            pattern = "(src:Document {doc_id: $doc_id})<-[:LINKS_TO*1..$depth]-(rel:Document)"
        else:
            pattern = "(src:Document {doc_id: $doc_id})-[:LINKS_TO*1..$depth]-(rel:Document)"

        # AGE does not support variable-length path variables directly in all
        # versions — use a fixed-depth approach via apoc or decompose with
        # multiple hops. For simplicity we use up to depth 5 with UNION.
        # This is a pragmatic approach until AGE matures its path functions.
        results: dict[str, dict] = {}
        for hop in range(1, min(depth, 5) + 1):
            if direction == "outgoing":
                arrow = f"-[:LINKS_TO*{hop}]->"
            elif direction == "incoming":
                arrow = f"<-[:LINKS_TO*{hop}]-"
            else:
                arrow = f"-[:LINKS_TO*{hop}]-"

            cypher = (
                f"MATCH (src:Document {{doc_id: $doc_id}}){arrow}(rel:Document) "
                f"WHERE rel.doc_id <> $doc_id "
                f"RETURN rel.doc_id AS doc_id, rel.file_name AS file_name, rel.title AS title"
            )
            rows = await self._cypher(
                conn,
                cypher,
                {"doc_id": doc_id},
                return_columns=["doc_id", "file_name", "title"],
            )
            for row in rows:
                # agtype values are returned as strings by asyncpg
                rid = _parse_agtype_str(str(row["doc_id"]))
                if rid not in results:
                    results[rid] = {
                        "doc_id": rid,
                        "file_name": _parse_agtype_str(str(row["file_name"])),
                        "title": _parse_agtype_str(str(row["title"])),
                        "hops": hop,
                    }
        return list(results.values())


def _parse_agtype_str(value: str) -> str:
    """Strip surrounding quotes from an agtype string value returned by asyncpg."""
    # AGE returns string values wrapped in double-quotes, e.g. '"intro.md"'
    stripped = value.strip()
    if stripped.startswith('"') and stripped.endswith('"'):
        return stripped[1:-1]
    return stripped
