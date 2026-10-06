# File: backend/app/infrastructure/persistence/sql_unit_of_work.py
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.application.unit_of_work import IUnitOfWork
from app.infrastructure.persistence.database import DatabaseSessionManager
from app.infrastructure.persistence.repositories.postgres_job_repo import PostgresJobRepository
from app.infrastructure.persistence.repositories.postgres_profile_repo import PostgresProfileRepository
from app.infrastructure.persistence.repositories.postgres_proxy_repo import PostgresProxyRepository
from app.infrastructure.persistence.repositories.postgres_task_repo import PostgresTaskRepository


class SqlAlchemyUnitOfWork(IUnitOfWork):
    def __init__(self, session_manager: DatabaseSessionManager):
        self._session_manager = session_manager
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        self._session = self._session_manager.session()
        self.jobs = PostgresJobRepository(self._session)
        self.tasks = PostgresTaskRepository(self._session)
        self.proxies = PostgresProxyRepository(self._session)
        self.profiles = PostgresProfileRepository(self._session)
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        try:
            if exc_type is not None:
                await self.rollback()
            else:
                await self.commit()
        finally:
            if self._session:
                await self._session.close()

    async def commit(self) -> None:
        if self._session:
            await self._session.commit()

    async def rollback(self) -> None:
        if self._session:
            await self._session.rollback()
