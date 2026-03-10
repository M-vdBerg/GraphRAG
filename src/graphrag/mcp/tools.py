"""MCP tool definitions for GraphRAG.

All tools are registered on the shared ``FastMCP`` instance imported from
``server.py``.  They share the pool and embedder via ``app_state`` which is
populated in the server lifespan.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def register_tools(mcp: FastMCP, state: dict[str, Any]) -> None:
    """Register all tools on *mcp*, closing over *state* for DB/embedder access."""

    pool = state["pool"]
    embedder = state["embedder"]
    chunk_repo = state["chunk_repo"]
    doc_repo = state["doc_repo"]
    age = state["age"]

    # ── 1. search ─────────────────────────────────────────────────────────────

    @mcp.tool()
    async def search(
        query: Annotated[str, Field(description="Natural language search query")],
        top_k: Annotated[int, Field(ge=1, le=50, description="Maximum number of results")] = 10,
        min_score: Annotated[
            float, Field(ge=0.0, le=1.0, description="Minimum cosine similarity score")
        ] = 0.0,
        doc_filter: Annotated[
            str | None, Field(description="Restrict search to a specific doc_id")
        ] = None,
    ) -> list[dict[str, Any]]:
        """Semantic vector search over all indexed chunks.

        Returns ranked chunks with parent document metadata and similarity scores.
        """
        query_vec = embedder.embed_query(query)
        async with pool.acquire() as conn:
            results = await chunk_repo.vector_search(
                conn,
                query_embedding=query_vec,
                top_k=top_k,
                min_score=min_score,
                doc_id_filter=doc_filter,
            )
        return [
            {
                "chunk_id": r.chunk_id,
                "doc_id": r.doc_id,
                "file_name": r.file_name,
                "document_title": r.document_title,
                "heading": r.heading,
                "content": r.content,
                "position": r.position,
                "score": round(r.score, 4),
            }
            for r in results
        ]

    # ── 2. get_document ───────────────────────────────────────────────────────

    @mcp.tool()
    async def get_document(
        doc_id: Annotated[str, Field(description="Document ID (SHA-256 hex)")]
    ) -> dict[str, Any]:
        """Retrieve all chunks of a document in order.

        Use ``list_documents`` to discover available doc_ids.
        """
        async with pool.acquire() as conn:
            doc = await doc_repo.get_by_id(conn, doc_id)
            if doc is None:
                return {"error": f"Document '{doc_id}' not found"}
            chunks = await chunk_repo.get_by_doc(conn, doc_id)
        return {
            "doc_id": doc.doc_id,
            "file_name": doc.file_name,
            "file_path": doc.file_path,
            "title": doc.title,
            "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
            "chunks": chunks,
        }

    # ── 3. list_documents ─────────────────────────────────────────────────────

    @mcp.tool()
    async def list_documents() -> list[dict[str, Any]]:
        """List all documents currently indexed in the graph."""
        async with pool.acquire() as conn:
            docs = await doc_repo.list_all(conn)
        return [
            {
                "doc_id": d["doc_id"],
                "file_name": d["file_name"],
                "title": d["title"],
                "updated_at": d["updated_at"].isoformat() if d.get("updated_at") else None,
                "chunk_count": d["chunk_count"],
            }
            for d in docs
        ]

    # ── 4. get_related ────────────────────────────────────────────────────────

    @mcp.tool()
    async def get_related(
        doc_id: Annotated[str, Field(description="Starting document ID")],
        depth: Annotated[int, Field(ge=1, le=5, description="Graph traversal depth")] = 2,
        direction: Annotated[
            Literal["both", "outgoing", "incoming"],
            Field(description="Edge direction to follow"),
        ] = "both",
    ) -> list[dict[str, Any]]:
        """Traverse LINKS_TO graph edges to find documents related to a given document.

        Results are deduplicated; the shortest hop count is reported for each.
        """
        async with pool.acquire() as conn:
            await conn.execute("LOAD 'age'")
            await conn.execute("SET search_path = ag_catalog, graphrag, public")
            results = await age.get_related_documents(conn, doc_id, depth, direction)
        return results

    # ── 5. get_chunk_context ──────────────────────────────────────────────────

    @mcp.tool()
    async def get_chunk_context(
        chunk_id: Annotated[str, Field(description="Chunk ID from a search result")],
        window: Annotated[
            int, Field(ge=1, le=5, description="Number of neighboring chunks before/after")
        ] = 1,
    ) -> dict[str, Any]:
        """Expand context around a search hit by fetching neighboring chunks.

        Returns the matched chunk plus up to *window* chunks before and after
        it within the same document, in document order.
        """
        async with pool.acquire() as conn:
            chunks = await chunk_repo.get_context_window(conn, chunk_id, window)
            if not chunks:
                return {"error": f"Chunk '{chunk_id}' not found"}
            doc_id = chunks[0].get("doc_id") if isinstance(chunks[0], dict) else None
            doc = await doc_repo.get_by_id(conn, doc_id) if doc_id else None

        return {
            "doc_id": doc_id,
            "document_title": doc.title if doc else None,
            "chunks": chunks,
        }
