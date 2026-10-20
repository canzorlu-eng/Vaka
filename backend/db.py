"""PostgreSQL connection pool (asyncpg). Schema is owned by Alembic (see migrations/)."""
import json
import logging
from typing import Optional

import asyncpg

from config import settings

logger = logging.getLogger(__name__)
_pool: Optional[asyncpg.Pool] = None


async def _init_conn(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def connect() -> None:
    global _pool
    _pool = await asyncpg.create_pool(
        settings.database_url, init=_init_conn,
        min_size=1, max_size=settings.db_pool_max,
        command_timeout=settings.db_command_timeout,
        max_inactive_connection_lifetime=300,
    )
    logger.info("database pool ready (max_size=%s)", settings.db_pool_max)


async def close() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database is not connected")
    return _pool


async def ping() -> bool:
    try:
        return await pool().fetchval("SELECT 1") == 1
    except Exception:  # noqa: BLE001
        return False


def pool_stats() -> dict:
    p = _pool
    if p is None:
        return {"size": 0, "idle": 0, "max": settings.db_pool_max}
    return {"size": p.get_size(), "idle": p.get_idle_size(), "max": p.get_max_size()}
