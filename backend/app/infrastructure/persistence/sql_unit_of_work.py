# File: backend/app/infrastructure/persistence/sql_unit_of_work.py
from typing import Any, AsyncContextManager, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.unit_of_work import (
    IAuthUnitOfWork,
    ISystemUnitOfWork,
    ISystemUnitOfWorkFactory,
    IUnitOfWork,
    IUnitOfWorkFactory,
    SystemPurpose,
)
from app.infrastructure.persistence.database import DatabaseSessionManager
from app.infrastructure.persistence.write_transaction import begin_write_transaction
from app.infrastructure.persistence.operator_uow import OperatorAuthUnitOfWork
from app.infrastructure.persistence.repositories.operator_session_repo import SqlOperatorSessionRepository
from app.infrastructure.persistence.repositories.artifact_repo import SqlArtifactRepository
from app.infrastructure.persistence.repositories.browser_session_repo import (
    BrowserSessionRepository,
)
from app.infrastructure.persistence.repositories.operator_account_repo import (
    SqlOperatorAccountRepository,
)
from app.infrastructure.persistence.repositories.postgres_profile_repo import (
    PostgresProfileRepository,
)
from app.infrastructure.persistence.repositories.postgres_proxy_repo import (
    PostgresProxyRepository,
)
from app.infrastructure.persistence.repositories.postgres_task_repo import (
    PostgresTaskRepository,
)
from app.infrastructure.persistence.repositories.control_repo import (
    SqlControlRepository,
)
from app.infrastructure.persistence.repositories.start_receipt_repo import (
    SqlTaskStartReceiptRepository,
)
from app.infrastructure.persistence.repositories.task_execution_repo import (
    SqlTaskExecutionRepository,
)
from app.infrastructure.persistence.repositories.task_query_repo import (
    SqlTaskQueryRepository,
)

DEFAULT_OPERATOR_ID = UUID("00000000-0000-0000-0000-000000000001")


class SqlAlchemyUnitOfWork(IUnitOfWork):
    def __init__(
        self,
        session_manager: DatabaseSessionManager,
        operator_id: Optional[UUID] = None,
        write: bool = False,
    ):
        self._session_manager = session_manager
        if not isinstance(operator_id, UUID):
            raise ValueError("A scoped unit of work requires an explicit owner UUID.")
        self._operator_id = operator_id
        self._write = write
        self._session: AsyncSession | None = None
        self._committed = False

    @property
    def operator_id(self) -> Optional[UUID]:
        return self._operator_id

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        self._session = self._session_manager.session()
        self._committed = False
        if self._write:
            try:
                await begin_write_transaction(self._session)
            except BaseException:
                await self._session.close()
                raise

        self.tasks = PostgresTaskRepository(self._session, self._operator_id)
        self.proxies = PostgresProxyRepository(self._session, self._operator_id)
        self.profiles = PostgresProfileRepository(self._session, self._operator_id)
        self.artifacts = SqlArtifactRepository(self._session, self._operator_id)
        self.browser_sessions = BrowserSessionRepository(self._session)
        self.accounts = SqlOperatorAccountRepository(self._session)
        self.sessions = SqlOperatorSessionRepository(self._session)
        self.task_queries = SqlTaskQueryRepository(self._session, self._operator_id)
        self.slot = SqlTaskExecutionRepository(self._session)
        self.start_receipts = SqlTaskStartReceiptRepository(self._session, self._operator_id)
        self.controls = SqlControlRepository(self._session, self._operator_id)
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        try:
            if exc_type is not None or not self._committed:
                await self.rollback()
        finally:
            if self._session:
                await self._session.close()

    async def commit(self) -> None:
        if self._session:
            await self._session.commit()
            self._committed = True

    async def rollback(self) -> None:
        if self._session:
            await self._session.rollback()


class SystemSqlUnitOfWork(SqlAlchemyUnitOfWork, ISystemUnitOfWork):
    def __init__(
        self, session_manager: DatabaseSessionManager, purpose: SystemPurpose
    ):
        super().__init__(session_manager, operator_id=DEFAULT_OPERATOR_ID, write=True)
        self._operator_id = None
        self.purpose = purpose


class ScopedUnitOfWorkFactory(IUnitOfWorkFactory):
    def __init__(self, session_manager: DatabaseSessionManager):
        self._session_manager = session_manager

    def owned(self, owner: UUID) -> AsyncContextManager[IUnitOfWork]:
        return SqlAlchemyUnitOfWork(self._session_manager, operator_id=owner, write=False)

    def request(self, principal: Any) -> AsyncContextManager[IUnitOfWork]:
        op_id = getattr(principal, "operator_id", principal)
        return SqlAlchemyUnitOfWork(self._session_manager, operator_id=op_id, write=True)

    def execution(self, grant: Any) -> AsyncContextManager[IUnitOfWork]:
        scope = getattr(grant, "scope", grant)
        op_id = getattr(scope, "operator_id", None)
        if not isinstance(op_id, UUID):
            raise ValueError("Execution UoW requires an explicit owner.")
        return SqlAlchemyUnitOfWork(self._session_manager, operator_id=op_id, write=True)

    def operator(
        self, id: UUID, *, write: bool = False
    ) -> AsyncContextManager[IUnitOfWork]:
        return SqlAlchemyUnitOfWork(
            self._session_manager, operator_id=id, write=write
        )

    def auth(self) -> AsyncContextManager[IAuthUnitOfWork]:
        return OperatorAuthUnitOfWork(self._session_manager.session())


class SystemUnitOfWorkFactory(ISystemUnitOfWorkFactory):
    def __init__(self, session_manager: DatabaseSessionManager):
        self._session_manager = session_manager

    def open(self, purpose: SystemPurpose) -> AsyncContextManager[ISystemUnitOfWork]:
        return SystemSqlUnitOfWork(self._session_manager, purpose)
