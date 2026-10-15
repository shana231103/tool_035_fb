# File: backend/app/domain/ports/browser_sessions.py
from abc import ABC, abstractmethod
from uuid import UUID
from app.domain.value_objects.browser_status import (
    BrowserReadiness, BrowserStatus, CleanupOutcome, ExternalCleanupConfirmation,
)


class IBrowserControl(ABC):
    @abstractmethod
    async def bootstrap(self) -> BrowserReadiness:
        raise NotImplementedError

    @abstractmethod
    async def assert_ready(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def assert_task_retriable(self, task_id: UUID) -> None:
        raise NotImplementedError

    @abstractmethod
    async def status(self, task_id: UUID | None = None) -> BrowserStatus:
        raise NotImplementedError

    @abstractmethod
    async def retry_cleanup(self, operation_id: UUID) -> CleanupOutcome:
        raise NotImplementedError

    @abstractmethod
    async def confirm_external_cleanup(self, confirmation: ExternalCleanupConfirmation) -> CleanupOutcome:
        raise NotImplementedError

    @abstractmethod
    async def shutdown(self) -> None:
        raise NotImplementedError
