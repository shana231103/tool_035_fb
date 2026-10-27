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

Base = declarative_base()


class DatabaseSessionManager:
    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None

    def init(self, db_url: str, echo: bool = False) -> None:
        connect_args = {}
        if "sqlite" in db_url:
            connect_args = {"check_same_thread": False}

        self._engine = create_async_engine(
            db_url,
            echo=echo,
            future=True,
            connect_args=connect_args,
        )
        if "sqlite" in db_url:
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
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

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
