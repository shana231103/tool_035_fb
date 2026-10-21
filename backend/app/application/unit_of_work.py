# File: backend/app/application/unit_of_work.py
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, AsyncContextManager, Optional
from uuid import UUID

from app.application.task_queries import ITaskQueries
from app.domain.ports.browser_ledger import IBrowserSessionLedger
from app.domain.ports.operator_security import IAccountRepository, ISessionRepository
from app.domain.ports.repositories import (
    IArtifactRepository,
    IOwnerProfileRepository,
    IProxyRepository,
    IReportTaskRepository,
)
from app.domain.ports.task_execution_ports import (
    IControlRepository,
    ITaskExecutionRepository,
    ITaskStartReceiptRepository,
)


class SystemPurpose(str, Enum):
    RECOVERY = "RECOVERY"
    PROVIDER_LEDGER = "PROVIDER_LEDGER"
    DISABLE_SWEEP = "DISABLE_SWEEP"
    LEGACY_ASSIGNMENT = "LEGACY_ASSIGNMENT"


class IUnitOfWork(ABC):
    tasks: IReportTaskRepository
    proxies: IProxyRepository
    profiles: IOwnerProfileRepository
    artifacts: IArtifactRepository
    browser_sessions: IBrowserSessionLedger
    accounts: IAccountRepository
    sessions: ISessionRepository
    task_queries: Optional[ITaskQueries] = None
    slot: Optional[ITaskExecutionRepository] = None
    start_receipts: Optional[ITaskStartReceiptRepository] = None
    controls: Optional[IControlRepository] = None

    @property
    def operator_id(self) -> Optional[UUID]:
        return None

    async def __aenter__(self) -> "IUnitOfWork":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None:
            await self.rollback()

    @abstractmethod
    async def commit(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def rollback(self) -> None:
        raise NotImplementedError


class IAuthUnitOfWork(ABC):
    accounts: IAccountRepository
    sessions: ISessionRepository

    async def __aenter__(self) -> "IAuthUnitOfWork":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None:
            await self.rollback()

    @abstractmethod
    async def commit(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def rollback(self) -> None:
        raise NotImplementedError


class ISystemUnitOfWork(IUnitOfWork):
    purpose: SystemPurpose


class IUnitOfWorkFactory(ABC):
    @abstractmethod
    def owned(self, owner: UUID) -> AsyncContextManager[IUnitOfWork]:
        raise NotImplementedError

    @abstractmethod
    def request(self, principal: Any) -> AsyncContextManager[IUnitOfWork]:
        raise NotImplementedError

    @abstractmethod
    def execution(self, grant: Any) -> AsyncContextManager[IUnitOfWork]:
        raise NotImplementedError

    @abstractmethod
    def operator(
        self, id: UUID, *, write: bool = False
    ) -> AsyncContextManager[IUnitOfWork]:
        raise NotImplementedError

    @abstractmethod
    def auth(self) -> AsyncContextManager[IAuthUnitOfWork]:
        raise NotImplementedError


class IAuthUnitOfWorkFactory(ABC):
    @abstractmethod
    def auth(self, *, write: bool = False) -> AsyncContextManager[IAuthUnitOfWork]:
        raise NotImplementedError


class ISystemUnitOfWorkFactory(ABC):
    @abstractmethod
    def open(
        self, purpose: SystemPurpose, *, write: bool = True
    ) -> AsyncContextManager[ISystemUnitOfWork]:
        raise NotImplementedError
