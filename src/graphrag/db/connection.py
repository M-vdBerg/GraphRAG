"""asyncpg connection pool with AGE and pgvector initialisation."""

from __future__ import annotations

import asyncpg

from graphrag.config import Settings


async def _init_connection(conn: asyncpg.Connection) -> None:  # type: ignore[type-arg]
    """Called by asyncpg for every new connection in the pool.

    Apache AGE requires its shared library to be loaded and its catalog schema
    to appear in search_path before any Cypher statement can execute.
    pgvector's ``vector`` type is available after extension creation, but
    setting search_path explicitly keeps things predictable.
    """
    await conn.execute("LOAD 'age'")
    await conn.execute("SET search_path = ag_catalog, graphrag, public")


async def create_pool(settings: Settings) -> asyncpg.Pool:  # type: ignore[type-arg]
    """Create and return an asyncpg connection pool."""
    dsn = (
        f"postgresql://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )
    return await asyncpg.create_pool(
        dsn=dsn,
        init=_init_connection,
        min_size=2,
        max_size=10,
        command_timeout=60,
    )
