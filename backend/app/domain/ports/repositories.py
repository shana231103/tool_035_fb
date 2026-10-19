# File: backend/app/domain/ports/repositories.py
from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import UUID
from app.domain.entities.owner_profile import OwnerProfile
from app.domain.entities.proxy_item import ProxyItem
from app.domain.entities.report_task import ReportTask
from app.domain.value_objects.enums import ProxyCountry
from app.domain.value_objects.operator_identity import ArtifactKind, ArtifactRecord


class IReportTaskRepository(ABC):
    @property
    def operator_id(self) -> Optional[UUID]:
        return None

    @abstractmethod
    async def get_by_id(self, task_id: UUID) -> Optional[ReportTask]:
        raise NotImplementedError

    @abstractmethod
    async def insert(self, task: ReportTask) -> None:
        raise NotImplementedError

    @abstractmethod
    async def save(
        self, task: ReportTask, *, expected_version: int, expected_attempt_id: Optional[UUID]
    ) -> None:
        raise NotImplementedError


class IProxyRepository(ABC):
    @property
    def operator_id(self) -> Optional[UUID]:
        return None

    @abstractmethod
    async def get_by_id(self, proxy_id: UUID) -> Optional[ProxyItem]:
        raise NotImplementedError

    @abstractmethod
    async def get_active_proxy(self, country: Optional[ProxyCountry] = None) -> Optional[ProxyItem]:
        raise NotImplementedError

    @abstractmethod
    async def list_all(self) -> List[ProxyItem]:
        raise NotImplementedError

    @abstractmethod
    async def save(self, proxy: ProxyItem) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, proxy_id: UUID) -> None:
        raise NotImplementedError


class IOwnerProfileRepository(ABC):
    @property
    def operator_id(self) -> Optional[UUID]:
        return None

    @abstractmethod
    async def get_by_id(self, profile_id: UUID) -> Optional[OwnerProfile]:
        raise NotImplementedError

    @abstractmethod
    async def list_all(self) -> List[OwnerProfile]:
        raise NotImplementedError

    @abstractmethod
    async def save(self, profile: OwnerProfile) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, profile_id: UUID) -> None:
        raise NotImplementedError


class IArtifactRepository(ABC):
    @property
    def operator_id(self) -> Optional[UUID]:
        return None

    @abstractmethod
    async def get_by_key(self, key: str, kind: ArtifactKind) -> Optional[ArtifactRecord]:
        raise NotImplementedError

    @abstractmethod
    async def add(self, record: ArtifactRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    async def list_for_task(self, task_id: UUID) -> List[ArtifactRecord]:
        raise NotImplementedError
