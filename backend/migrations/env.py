"""Alembic environment (async). Schema is managed with raw SQL migrations - there are no ORM models."""
import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

config = context.config
# Programmatic runs (app start-up) keep the application's own JSON logging; only the CLI applies alembic.ini logging.
if config.config_file_name is not None and not config.attributes.get("skip_logging"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def _url() -> str:
    url = os.environ.get("DATABASE_URL") or os.environ.get("ALEMBIC_DATABASE_URL")
    if not url:
        from config import settings
        url = settings.database_url
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix):]
    return url


def _do_run(connection) -> None:
    context.configure(connection=connection, target_metadata=None, transaction_per_migration=True)
    with context.begin_transaction():
        context.run_migrations()


async def _run_online() -> None:
    engine = create_async_engine(_url(), poolclass=pool.NullPool)
    async with engine.connect() as conn:
        await conn.run_sync(_do_run)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(url=_url(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(_run_online())
