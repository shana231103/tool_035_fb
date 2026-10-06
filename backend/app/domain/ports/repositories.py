# File: backend/app/domain/ports/repositories.py
from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import UUID
from app.domain.entities.batch_job import BatchJob
from app.domain.entities.owner_profile import OwnerProfile
from app.domain.entities.proxy_item import ProxyItem
from app.domain.entities.report_task import ReportTask
from app.domain.value_objects.enums import ProxyCountry


class IBatchJobRepository(ABC):
    @abstractmethod
    async def get_by_id(self, job_id: UUID) -> Optional[BatchJob]:
        pass

    @abstractmethod
    async def save(self, job: BatchJob) -> None:
        pass

    @abstractmethod
    async def list_jobs(self, limit: int = 50, offset: int = 0) -> List[BatchJob]:
        pass

    @abstractmethod
    async def delete(self, job_id: UUID) -> None:
        pass


class IReportTaskRepository(ABC):
    @abstractmethod
    async def get_by_id(self, task_id: UUID) -> Optional[ReportTask]:
        pass

    @abstractmethod
    async def save(self, task: ReportTask) -> None:
        pass

    @abstractmethod
    async def get_next_queued_tasks(self, job_id: UUID, limit: int = 10) -> List[ReportTask]:
        pass

    @abstractmethod
    async def list_tasks_by_job(self, job_id: UUID) -> List[ReportTask]:
        pass


class IProxyRepository(ABC):
    @abstractmethod
    async def get_by_id(self, proxy_id: UUID) -> Optional[ProxyItem]:
        pass

    @abstractmethod
    async def get_active_proxy(self, country: Optional[ProxyCountry] = None) -> Optional[ProxyItem]:
        pass

    @abstractmethod
    async def list_all(self) -> List[ProxyItem]:
        pass

    @abstractmethod
    async def save(self, proxy: ProxyItem) -> None:
        pass

    @abstractmethod
    async def delete(self, proxy_id: UUID) -> None:
        pass


class IOwnerProfileRepository(ABC):
    @abstractmethod
    async def get_by_id(self, profile_id: UUID) -> Optional[OwnerProfile]:
        pass

    @abstractmethod
    async def list_all(self) -> List[OwnerProfile]:
        pass

    @abstractmethod
    async def save(self, profile: OwnerProfile) -> None:
        pass

    @abstractmethod
    async def delete(self, profile_id: UUID) -> None:
        pass
