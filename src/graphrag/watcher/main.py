"""Entry point for the watcher service (``python -m graphrag.watcher.main``)."""

from __future__ import annotations

import asyncio
import logging
import signal

from graphrag.config import settings
from graphrag.db.connection import create_pool
from graphrag.db.repositories import ChunkRepository, DocumentRepository
from graphrag.embeddings.embedder import Embedder
from graphrag.graph.age_client import AGEClient
from graphrag.parser.markdown_parser import MarkdownParser
from graphrag.watcher.file_watcher import DocumentProcessor, FileWatcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    pool = await create_pool(settings)
    embedder = Embedder(
        model_name=settings.embedding_model,
        device=settings.embedding_device,
        batch_size=settings.embedding_batch_size,
    )
    processor = DocumentProcessor(
        pool=pool,
        embedder=embedder,
        parser=MarkdownParser(),
        age=AGEClient(),
        doc_repo=DocumentRepository(),
        chunk_repo=ChunkRepository(),
    )
    watcher = FileWatcher(processor)

    loop = asyncio.get_running_loop()

    # Graceful shutdown on SIGTERM / SIGINT
    stop_event = asyncio.Event()

    def _shutdown(*_: object) -> None:
        logger.info("Shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _shutdown)

    await watcher.initial_scan(settings.docs_path, settings.watch_recursive)
    watcher.start(settings.docs_path, loop, settings.watch_recursive)

    logger.info("Watcher running — waiting for file events")
    await stop_event.wait()

    watcher.stop()
    await pool.close()
    logger.info("Watcher stopped")


if __name__ == "__main__":
    asyncio.run(main())
