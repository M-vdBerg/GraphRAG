"""MCP server entry point (``python -m graphrag.mcp.server``).

Transport: HTTP / SSE via FastMCP.
The server loads the embedding model once on startup and shares the asyncpg
pool across all tool calls via a module-level state dict.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from mcp.server.fastmcp import FastMCP

from graphrag.config import settings
from graphrag.db.connection import create_pool
from graphrag.db.repositories import ChunkRepository, DocumentRepository
from graphrag.embeddings.embedder import Embedder
from graphrag.graph.age_client import AGEClient
from graphrag.mcp.tools import register_tools

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

# ─── App state shared with tools ──────────────────────────────────────────────
_state: dict = {}


@asynccontextmanager
async def lifespan(_app: object) -> AsyncIterator[None]:
    logger.info("Starting GraphRAG MCP server")
    _state["pool"] = await create_pool(settings)
    _state["embedder"] = Embedder(
        model_name=settings.embedding_model,
        device=settings.embedding_device,
        batch_size=settings.embedding_batch_size,
        precision=settings.embedding_precision,
    )
    _state["chunk_repo"] = ChunkRepository()
    _state["doc_repo"] = DocumentRepository()
    _state["age"] = AGEClient()
    logger.info("MCP server ready — listening on %s:%d", settings.mcp_host, settings.mcp_port)
    yield
    await _state["pool"].close()
    logger.info("MCP server shut down")


mcp = FastMCP(
    "GraphRAG",
    lifespan=lifespan,
)

register_tools(mcp, _state)


def run() -> None:
    import uvicorn

    uvicorn.run(
        mcp.sse_app(),
        host=settings.mcp_host,
        port=settings.mcp_port,
        log_level="info",
    )


if __name__ == "__main__":
    run()
