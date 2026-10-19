# File: backend/app/infrastructure/persistence/operator_uow.py
"""Auth Unit of Work implementation for accounts and session transactions."""

from typing import Any, AsyncContextManager
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.unit_of_work import IAuthUnitOfWork
from app.infrastructure.persistence.repositories.operator_account_repo import (
    SqlOperatorAccountRepository,
)
from app.infrastructure.persistence.repositories.operator_session_repo import (
    SqlOperatorSessionRepository,
)
from app.infrastructure.persistence.write_transaction import begin_write_transaction


class OperatorAuthUnitOfWork(IAuthUnitOfWork):
    """Unit of work for atomic account credential and session issuance/revocation."""

    def __init__(self, session: AsyncSession, write: bool = False):
        self._session = session
        self._write = write
        self.accounts = SqlOperatorAccountRepository(session)
        self.sessions = SqlOperatorSessionRepository(session)
        self._committed = False

    async def __aenter__(self) -> "OperatorAuthUnitOfWork":
        self._committed = False
        if self._write:
            try:
                await begin_write_transaction(self._session)
            except BaseException:
                await self._session.close()
                raise
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        try:
            if exc_type is not None or not self._committed:
                await self.rollback()
        finally:
            await self._session.close()

    async def commit(self) -> None:
        await self._session.commit()
        self._committed = True

    async def rollback(self) -> None:
        await self._session.rollback()


class AuthUnitOfWorkFactory:
    """Factory creating individual short-lived IAuthUnitOfWork sessions."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]):
        self._sessionmaker = sessionmaker

    def auth(self, *, write: bool = False) -> OperatorAuthUnitOfWork:
        session = self._sessionmaker()
        return OperatorAuthUnitOfWork(session, write=write)

    def __call__(self, *, write: bool = False) -> OperatorAuthUnitOfWork:
        """Compatibility call creating default auth UoW."""
        return self.auth(write=write)
