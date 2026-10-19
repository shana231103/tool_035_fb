# File: backend/alembic_postgres/env.py
"""Independent PostgreSQL migrations for new, empty application installations."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alembic import context
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings
from app.infrastructure.persistence.database_connection import build_async_engine_options


def migrate(connection):
    context.configure(connection=connection)
    # Concurrent deployment commands share one transaction and DDL lock.
    with context.begin_transaction():
        connection.execute(text("SELECT pg_advisory_xact_lock(35005, 1)"))
        context.run_migrations()


async def online():
    url, options = build_async_engine_options(
        settings.database_migration_url or settings.database_url, migration=True
    )
    if url.get_backend_name() != "postgresql":
        raise RuntimeError("PostgreSQL migrations require a PostgreSQL DATABASE_URL.")
    engine = create_async_engine(url, **options)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(migrate)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Use online migrations to validate the empty PostgreSQL target.")
else:
    asyncio.run(online())
