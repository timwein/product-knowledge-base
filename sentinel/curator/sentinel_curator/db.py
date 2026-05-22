"""Async Postgres helpers — thin wrapper over asyncpg.

The curator service holds one connection pool for the lifetime of the
process; the scripts in sentinel/scripts/ open a one-shot connection.
"""

from __future__ import annotations

import asyncpg

from .config import settings


async def connect() -> asyncpg.Connection:
    """Open a single connection. Use for one-off scripts."""
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not set")
    return await asyncpg.connect(settings.database_url)


_pool: asyncpg.Pool | None = None


async def pool() -> asyncpg.Pool:
    """Lazily create a process-wide connection pool. Use from the API."""
    global _pool
    if _pool is None:
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL is not set")
        _pool = await asyncpg.create_pool(
            settings.database_url,
            min_size=1,
            max_size=10,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
