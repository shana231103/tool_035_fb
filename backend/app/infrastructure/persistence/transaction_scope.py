# File: backend/app/infrastructure/persistence/transaction_scope.py
"""Explicit SQLite and SQL transaction control utilities."""

from contextlib import asynccontextmanager
from typing import AsyncIterator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession


@asynccontextmanager
async def immediate_transaction(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    """Begin an immediate transaction before any authoritative reads.
    
    In SQLite, BEGIN IMMEDIATE acquires a reserved lock immediately, preventing
    deadlocks and stale snapshot write conflicts during serialized operations.
    """
    bind = session.bind
    is_sqlite = bind and "sqlite" in bind.dialect.name
    conn: AsyncConnection = await session.connection()
    if is_sqlite and not session.in_transaction():
        await conn.execute(text("BEGIN IMMEDIATE"))
    elif not session.in_transaction():
        await session.begin()
    try:
        yield session
    except Exception:
        if session.in_transaction():
            await session.rollback()
        raise


async def ensure_sqlite_foreign_keys(conn: AsyncConnection) -> None:
    """Ensure PRAGMA foreign_keys is enabled on the current SQLite connection."""
    if "sqlite" in conn.dialect.name:
        await conn.execute(text("PRAGMA foreign_keys = ON"))
        row = (await conn.execute(text("PRAGMA foreign_keys"))).scalar()
        if not row:
            raise RuntimeError("Failed to enable SQLite foreign key constraints.")
