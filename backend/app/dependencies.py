"""
FastAPI dependency providers.

Import and use these in route handlers for DI.
"""
from __future__ import annotations

from typing import AsyncGenerator

import redis.asyncio as aioredis

from app.config import get_settings
from app.observability.logging import get_logger

logger = get_logger(__name__)

_redis_pool: aioredis.ConnectionPool | None = None


def _get_redis_pool() -> aioredis.ConnectionPool:
    global _redis_pool
    if _redis_pool is None:
        settings = get_settings()
        _redis_pool = aioredis.ConnectionPool.from_url(
            str(settings.redis_url),
            max_connections=20,
            decode_responses=True,
        )
        logger.info("redis_pool_created")
    return _redis_pool


async def get_redis_client() -> AsyncGenerator[aioredis.Redis, None]:
    """Yield a Redis client from the shared connection pool."""
    pool = _get_redis_pool()
    client = aioredis.Redis(connection_pool=pool)
    try:
        yield client
    finally:
        await client.aclose()


async def close_redis_pool() -> None:
    """Disconnect the Redis pool.  Call on application shutdown."""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None
        logger.info("redis_pool_closed")
