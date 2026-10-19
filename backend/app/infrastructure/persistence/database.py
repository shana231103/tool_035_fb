# File: backend/app/infrastructure/persistence/database.py
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy import event
from app.infrastructure.persistence.database_connection import build_async_engine_options

Base = declarative_base()


class DatabaseSessionManager:
    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None

    def init(self, db_url: str, echo: bool = False) -> None:
        url, options = build_async_engine_options(db_url, echo=echo)
        self._engine = create_async_engine(url, **options)
        if url.get_backend_name() == "sqlite":
            @event.listens_for(self._engine.sync_engine, "connect")
            def configure_sqlite(connection, _record):
                cursor = connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()
        self._sessionmaker = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    async def close(self) -> None:
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._sessionmaker = None

    async def create_all_tables(self) -> None:
        if not self._engine:
            raise RuntimeError("Database engine is not initialized.")
        if self._engine.dialect.name != "sqlite":
            raise RuntimeError(
                "Initialize PostgreSQL explicitly: python -m alembic "
                "-c backend/alembic_postgres.ini upgrade head"
            )
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            def ensure_alembic_stamp(connection):
                from sqlalchemy import inspect, text
                inspector = inspect(connection)
                tables = set(inspector.get_table_names())
                if "alembic_version" not in tables:
                    connection.execute(text(
                        "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL, "
                        "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
                    ))
                    connection.execute(text(
                        "INSERT INTO alembic_version (version_num) VALUES ('006_single_task_repair')"
                    ))
                else:
                    revisions = set(connection.execute(text("SELECT version_num FROM alembic_version")).scalars())
                    if not revisions:
                        connection.execute(text(
                            "INSERT INTO alembic_version (version_num) VALUES ('006_single_task_repair')"
                        ))
                if "operator_accounts" in tables:
                    acc_rows = connection.execute(text("SELECT id FROM operator_accounts WHERE id = '00000000-0000-0000-0000-000000000001'")).fetchall()
                    if not acc_rows:
                        connection.execute(text(
                            "INSERT INTO operator_accounts "
                            "(id, username_key, username_display, password_hash, status, auth_version, run_version, created_at, updated_at) "
                            "VALUES ('00000000-0000-0000-0000-000000000001', 'system_default', 'system_default', 'dummy_hash', 'QUARANTINED', 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                        ))
            await conn.run_sync(ensure_alembic_stamp)

    async def validate_schema(self, validator) -> None:
        if not self._engine:
            raise RuntimeError("Database engine is not initialized.")
        async with self._engine.connect() as connection:
            await connection.run_sync(validator)

    def session(self) -> AsyncSession:
        if not self._sessionmaker:
            raise RuntimeError("Database sessionmaker is not initialized.")
        return self._sessionmaker()


db_manager = DatabaseSessionManager()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with db_manager.session() as session:
        yield session
