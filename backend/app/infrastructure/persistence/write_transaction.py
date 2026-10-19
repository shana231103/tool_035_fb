# File: backend/app/infrastructure/persistence/write_transaction.py
"""Cross-dialect serialization for short application write transactions."""

from sqlalchemy import text


async def begin_write_transaction(session) -> None:
    connection = await session.connection()
    if connection.dialect.name == "sqlite":
        await connection.exec_driver_sql("BEGIN IMMEDIATE")
    elif connection.dialect.name == "postgresql":
        # Same key for auth and resource writes, mirroring SQLite's one writer.
        # Released by COMMIT/ROLLBACK, never held during browser/network work.
        await connection.execute(text("SELECT pg_advisory_xact_lock(35005, 2)"))
