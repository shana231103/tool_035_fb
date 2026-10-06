# File: backend/app/application/unit_of_work.py
from abc import ABC, abstractmethod
from typing import Any
from app.domain.ports.repositories import (
    IBatchJobRepository,
    IOwnerProfileRepository,
    IProxyRepository,
    IReportTaskRepository,
)


class IUnitOfWork(ABC):
    jobs: IBatchJobRepository
    tasks: IReportTaskRepository
    proxies: IProxyRepository
    profiles: IOwnerProfileRepository

    async def __aenter__(self) -> "IUnitOfWork":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None:
            await self.rollback()
        else:
            await self.commit()

    @abstractmethod
    async def commit(self) -> None:
        pass

    @abstractmethod
    async def rollback(self) -> None:
        pass
