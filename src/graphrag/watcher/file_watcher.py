"""File-system watcher and document ingestion pipeline.

Threading model
────────────────
``watchdog`` dispatches events from a background OS-thread. The actual
database/embedding work is async. We bridge the two worlds by capturing the
running asyncio event loop in the main thread and using
``asyncio.run_coroutine_threadsafe()`` to submit coroutines from the watchdog
thread.

Initial scan
────────────
On startup all ``.md`` files found in ``docs_path`` are processed through the
same ``process_file`` pipeline, so the graph reflects the current state of the
folder even if files were changed while the watcher was not running.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from datetime import datetime, timezone

import asyncpg
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from graphrag.db.repositories import ChunkRecord, ChunkRepository, DocumentRecord, DocumentRepository
from graphrag.embeddings.embedder import Embedder
from graphrag.graph.age_client import AGEClient
from graphrag.graph.schema import ChunkNode, DocumentNode
from graphrag.parser.markdown_parser import MarkdownParser

logger = logging.getLogger(__name__)


# ─── DocumentProcessor ────────────────────────────────────────────────────────

class DocumentProcessor:
    """Orchestrates parse → embed → graph upsert for a single file."""

    def __init__(
        self,
        pool: asyncpg.Pool,  # type: ignore[type-arg]
        embedder: Embedder,
        parser: MarkdownParser,
        age: AGEClient,
        doc_repo: DocumentRepository,
        chunk_repo: ChunkRepository,
    ) -> None:
        self._pool = pool
        self._embedder = embedder
        self._parser = parser
        self._age = age
        self._doc_repo = doc_repo
        self._chunk_repo = chunk_repo

    async def process_file(self, file_path: str) -> None:
        """Ingest or re-ingest a markdown file into the graph."""
        if not os.path.isfile(file_path):
            logger.warning("process_file called on non-existent path: %s", file_path)
            return

        file_hash = _hash_file(file_path)
        doc_id = _hash_str(file_path)

        parsed = self._parser.parse(file_path)

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Reload AGE inside the transaction for safety
                await conn.execute("LOAD 'age'")
                await conn.execute("SET search_path = ag_catalog, graphrag, public")

                doc_record = DocumentRecord(
                    doc_id=doc_id,
                    file_path=file_path,
                    file_name=os.path.basename(file_path),
                    title=parsed.title,
                    file_hash=file_hash,
                )
                changed = await self._doc_repo.upsert(conn, doc_record)

                if not changed:
                    logger.debug("Skipping unchanged file: %s", file_path)
                    return

                logger.info("Processing %s", file_path)

                # Remove old chunks (SQL cascade + AGE graph)
                await self._chunk_repo.delete_by_doc(conn, doc_id)
                await self._age.delete_document(conn, doc_id)

                # Upsert Document vertex
                doc_node = DocumentNode(
                    doc_id=doc_id,
                    file_path=file_path,
                    file_name=os.path.basename(file_path),
                    title=parsed.title,
                    updated_at=datetime.now(timezone.utc).isoformat(),
                )
                await self._age.upsert_document(conn, doc_node)

                if not parsed.chunks:
                    logger.debug("No chunks found in %s", file_path)
                    return

                # Embed all chunks in one batched call
                texts = [c.content for c in parsed.chunks]
                embeddings = self._embedder.embed(texts)

                chunk_ids: list[str] = []
                for chunk, embedding in zip(parsed.chunks, embeddings):
                    chunk_id = _hash_str(f"{doc_id}:{chunk.heading}:{chunk.position}")
                    chunk_ids.append(chunk_id)

                    sql_chunk = ChunkRecord(
                        chunk_id=chunk_id,
                        doc_id=doc_id,
                        heading=chunk.heading,
                        position=chunk.position,
                        content=chunk.content,
                        token_count=chunk.token_count,
                        embedding=embedding,
                    )
                    await self._chunk_repo.upsert(conn, sql_chunk)

                    age_chunk = ChunkNode(
                        chunk_id=chunk_id,
                        doc_id=doc_id,
                        heading=chunk.heading,
                        position=chunk.position,
                        content=chunk.content,
                        token_count=chunk.token_count,
                    )
                    await self._age.upsert_chunk(conn, age_chunk)
                    await self._age.create_has_chunk_edge(conn, doc_id, chunk_id, chunk.position)

                await self._age.create_next_chunk_edges(conn, chunk_ids)

                # Resolve and store markdown hyperlinks
                for anchor, abs_target in parsed.links:
                    tgt_doc_id = _hash_str(abs_target)
                    tgt_record = await self._doc_repo.get_by_path(conn, abs_target)
                    if tgt_record is None:
                        logger.debug(
                            "Link target not yet indexed, skipping edge: %s -> %s",
                            file_path,
                            abs_target,
                        )
                        continue
                    await self._age.create_links_to_edge(
                        conn, doc_id, tgt_doc_id, anchor, abs_target
                    )
                    await conn.execute(
                        """
                        INSERT INTO graphrag.doc_links (src_doc_id, tgt_doc_id, anchor, href)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT DO NOTHING
                        """,
                        doc_id,
                        tgt_doc_id,
                        anchor,
                        abs_target,
                    )

        logger.info("Finished processing %s (%d chunks)", file_path, len(chunk_ids))

    async def delete_file(self, file_path: str) -> None:
        """Remove a document and all related data from the graph."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("LOAD 'age'")
                await conn.execute("SET search_path = ag_catalog, graphrag, public")

                doc_id = _hash_str(file_path)
                await self._age.delete_document(conn, doc_id)
                await self._doc_repo.delete(conn, doc_id)

        logger.info("Deleted document from graph: %s", file_path)


# ─── watchdog event handler ───────────────────────────────────────────────────

class MarkdownEventHandler(FileSystemEventHandler):
    def __init__(self, processor: DocumentProcessor, loop: asyncio.AbstractEventLoop) -> None:
        super().__init__()
        self._processor = processor
        self._loop = loop

    def _submit(self, coro: object) -> None:
        asyncio.run_coroutine_threadsafe(coro, self._loop)  # type: ignore[arg-type]

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory and _is_markdown(str(event.src_path)):
            self._submit(self._processor.process_file(str(event.src_path)))

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory and _is_markdown(str(event.src_path)):
            self._submit(self._processor.process_file(str(event.src_path)))

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory and _is_markdown(str(event.src_path)):
            self._submit(self._processor.delete_file(str(event.src_path)))

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            src = str(event.src_path)
            dest = str(event.dest_path)  # type: ignore[attr-defined]
            if _is_markdown(src):
                self._submit(self._processor.delete_file(src))
            if _is_markdown(dest):
                self._submit(self._processor.process_file(dest))


# ─── FileWatcher ──────────────────────────────────────────────────────────────

class FileWatcher:
    def __init__(self, processor: DocumentProcessor) -> None:
        self._processor = processor
        self._observer: Observer | None = None

    async def initial_scan(self, docs_path: str, recursive: bool = True) -> None:
        """Process all existing .md files on startup."""
        logger.info("Running initial scan of %s", docs_path)
        for root, _dirs, files in os.walk(docs_path) if recursive else [(docs_path, [], os.listdir(docs_path))]:
            for name in files:
                if _is_markdown(name):
                    await self._processor.process_file(os.path.join(root, name))

    def start(self, docs_path: str, loop: asyncio.AbstractEventLoop, recursive: bool = True) -> None:
        handler = MarkdownEventHandler(self._processor, loop)
        self._observer = Observer()
        self._observer.schedule(handler, docs_path, recursive=recursive)
        self._observer.start()
        logger.info("Watching %s (recursive=%s)", docs_path, recursive)

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join()


# ─── Utilities ────────────────────────────────────────────────────────────────

def _hash_file(path: str) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            sha.update(block)
    return sha.hexdigest()


def _hash_str(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _is_markdown(path: str) -> bool:
    return path.lower().endswith(".md")
