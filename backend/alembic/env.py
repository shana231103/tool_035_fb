# File: backend/alembic/env.py
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings
from app.infrastructure.persistence.models import Base
from app.infrastructure.persistence.database_connection import build_async_engine_options

config = context.config
target_metadata = Base.metadata


def migrate(connection):
    context.configure(connection=connection, target_metadata=target_metadata,
                      render_as_batch=connection.dialect.name == "sqlite")
    with context.begin_transaction():
        context.run_migrations()


async def online():
    url, options = build_async_engine_options(
        settings.database_migration_url or settings.database_url, migration=True
    )
    if url.get_backend_name() != "sqlite":
        raise RuntimeError("For a new PostgreSQL database use backend/alembic_postgres.ini.")
    engine = create_async_engine(url, **options)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(migrate)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Use online migrations: baseline inspects existing legacy tables.")
else:
    asyncio.run(online())
