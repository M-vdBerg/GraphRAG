"""SQL (non-Cypher) repository classes for documents and chunks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg


# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class DocumentRecord:
    doc_id: str
    file_path: str
    file_name: str
    title: str | None
    file_hash: str
    updated_at: datetime | None = None


@dataclass
class ChunkRecord:
    chunk_id: str
    doc_id: str
    heading: str | None
    position: int
    content: str
    token_count: int | None
    embedding: list[float]


@dataclass
class ChunkSearchResult:
    chunk_id: str
    doc_id: str
    file_name: str
    document_title: str | None
    heading: str | None
    position: int
    content: str
    token_count: int | None
    score: float


# ─── DocumentRepository ───────────────────────────────────────────────────────

class DocumentRepository:
    async def upsert(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        doc: DocumentRecord,
    ) -> bool:
        """Insert or update a document record.

        Returns True if the content changed (file_hash differs from stored),
        False if the document already exists with the same hash.
        """
        existing = await conn.fetchrow(
            "SELECT file_hash FROM graphrag.documents WHERE doc_id = $1",
            doc.doc_id,
        )
        if existing and existing["file_hash"] == doc.file_hash:
            return False  # unchanged

        await conn.execute(
            """
            INSERT INTO graphrag.documents (doc_id, file_path, file_name, title, file_hash, updated_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            ON CONFLICT (doc_id) DO UPDATE SET
                file_path  = EXCLUDED.file_path,
                file_name  = EXCLUDED.file_name,
                title      = EXCLUDED.title,
                file_hash  = EXCLUDED.file_hash,
                updated_at = NOW()
            """,
            doc.doc_id,
            doc.file_path,
            doc.file_name,
            doc.title,
            doc.file_hash,
        )
        return True

    async def delete(self, conn: asyncpg.Connection, doc_id: str) -> None:  # type: ignore[type-arg]
        """Delete a document and cascade to its chunks and links."""
        await conn.execute(
            "DELETE FROM graphrag.documents WHERE doc_id = $1",
            doc_id,
        )

    async def get_by_path(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        file_path: str,
    ) -> DocumentRecord | None:
        row = await conn.fetchrow(
            "SELECT doc_id, file_path, file_name, title, file_hash, updated_at "
            "FROM graphrag.documents WHERE file_path = $1",
            file_path,
        )
        if row is None:
            return None
        return DocumentRecord(
            doc_id=row["doc_id"],
            file_path=row["file_path"],
            file_name=row["file_name"],
            title=row["title"],
            file_hash=row["file_hash"],
            updated_at=row["updated_at"],
        )

    async def get_by_id(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        doc_id: str,
    ) -> DocumentRecord | None:
        row = await conn.fetchrow(
            "SELECT doc_id, file_path, file_name, title, file_hash, updated_at "
            "FROM graphrag.documents WHERE doc_id = $1",
            doc_id,
        )
        if row is None:
            return None
        return DocumentRecord(
            doc_id=row["doc_id"],
            file_path=row["file_path"],
            file_name=row["file_name"],
            title=row["title"],
            file_hash=row["file_hash"],
            updated_at=row["updated_at"],
        )

    async def list_all(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
    ) -> list[dict]:
        rows = await conn.fetch(
            """
            SELECT d.doc_id, d.file_name, d.title, d.updated_at,
                   COUNT(c.chunk_id) AS chunk_count
            FROM graphrag.documents d
            LEFT JOIN graphrag.chunks c USING (doc_id)
            GROUP BY d.doc_id, d.file_name, d.title, d.updated_at
            ORDER BY d.file_name
            """
        )
        return [dict(r) for r in rows]


# ─── ChunkRepository ──────────────────────────────────────────────────────────

class ChunkRepository:
    async def upsert(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        chunk: ChunkRecord,
    ) -> None:
        await conn.execute(
            """
            INSERT INTO graphrag.chunks
                (chunk_id, doc_id, heading, position, content, token_count, embedding, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7::vector, NOW())
            ON CONFLICT (chunk_id) DO UPDATE SET
                heading     = EXCLUDED.heading,
                position    = EXCLUDED.position,
                content     = EXCLUDED.content,
                token_count = EXCLUDED.token_count,
                embedding   = EXCLUDED.embedding
            """,
            chunk.chunk_id,
            chunk.doc_id,
            chunk.heading,
            chunk.position,
            chunk.content,
            chunk.token_count,
            str(chunk.embedding),  # asyncpg needs the vector as a string literal
        )

    async def delete_by_doc(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        doc_id: str,
    ) -> None:
        await conn.execute(
            "DELETE FROM graphrag.chunks WHERE doc_id = $1",
            doc_id,
        )

    async def get_by_doc(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        doc_id: str,
    ) -> list[dict]:
        rows = await conn.fetch(
            """
            SELECT chunk_id, doc_id, heading, position, content, token_count
            FROM graphrag.chunks
            WHERE doc_id = $1
            ORDER BY position
            """,
            doc_id,
        )
        return [dict(r) for r in rows]

    async def get_context_window(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        chunk_id: str,
        window: int = 1,
    ) -> list[dict]:
        """Return chunk + up to `window` neighbors before/after within the same doc."""
        anchor = await conn.fetchrow(
            "SELECT doc_id, position FROM graphrag.chunks WHERE chunk_id = $1",
            chunk_id,
        )
        if anchor is None:
            return []
        rows = await conn.fetch(
            """
            SELECT chunk_id, heading, position, content
            FROM graphrag.chunks
            WHERE doc_id = $1
              AND position BETWEEN $2 AND $3
            ORDER BY position
            """,
            anchor["doc_id"],
            anchor["position"] - window,
            anchor["position"] + window,
        )
        return [
            {**dict(r), "is_match": r["chunk_id"] == chunk_id}
            for r in rows
        ]

    async def vector_search(
        self,
        conn: asyncpg.Connection,  # type: ignore[type-arg]
        query_embedding: list[float],
        top_k: int = 10,
        min_score: float = 0.0,
        doc_id_filter: str | None = None,
    ) -> list[ChunkSearchResult]:
        """Cosine similarity search over all chunk embeddings."""
        embedding_str = str(query_embedding)
        if doc_id_filter:
            rows = await conn.fetch(
                """
                SELECT c.chunk_id, c.doc_id, d.file_name, d.title AS document_title,
                       c.heading, c.position, c.content, c.token_count,
                       1 - (c.embedding <=> $1::vector) AS score
                FROM graphrag.chunks c
                JOIN graphrag.documents d USING (doc_id)
                WHERE c.doc_id = $2
                  AND 1 - (c.embedding <=> $1::vector) >= $3
                ORDER BY c.embedding <=> $1::vector
                LIMIT $4
                """,
                embedding_str,
                doc_id_filter,
                min_score,
                top_k,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT c.chunk_id, c.doc_id, d.file_name, d.title AS document_title,
                       c.heading, c.position, c.content, c.token_count,
                       1 - (c.embedding <=> $1::vector) AS score
                FROM graphrag.chunks c
                JOIN graphrag.documents d USING (doc_id)
                WHERE 1 - (c.embedding <=> $1::vector) >= $2
                ORDER BY c.embedding <=> $1::vector
                LIMIT $3
                """,
                embedding_str,
                min_score,
                top_k,
            )
        return [
            ChunkSearchResult(
                chunk_id=r["chunk_id"],
                doc_id=r["doc_id"],
                file_name=r["file_name"],
                document_title=r["document_title"],
                heading=r["heading"],
                position=r["position"],
                content=r["content"],
                token_count=r["token_count"],
                score=float(r["score"]),
            )
            for r in rows
        ]
