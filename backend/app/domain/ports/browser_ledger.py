# File: backend/app/domain/ports/browser_ledger.py
from abc import ABC, abstractmethod
from uuid import UUID
from app.domain.value_objects.browser_session import BrowserSessionMutation, BrowserSessionRecord
from app.domain.value_objects.browser_status import BrowserBootstrapSnapshot, BrowserLedgerCounts, RuntimeBinding


class IBrowserSessionLedger(ABC):
    @abstractmethod
    async def read_bootstrap_snapshot(self, limit: int = 1000) -> BrowserBootstrapSnapshot:
        raise NotImplementedError

    @abstractmethod
    async def initialize_binding_if_empty(self, binding: RuntimeBinding) -> RuntimeBinding:
        raise NotImplementedError

    @abstractmethod
    async def reserve(self, record: BrowserSessionRecord, limit: int) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get(self, operation_id: UUID) -> BrowserSessionRecord | None:
        raise NotImplementedError

    @abstractmethod
    async def get_unclosed_for_task(self, task_id: UUID) -> tuple[BrowserSessionRecord, ...]:
        raise NotImplementedError

    @abstractmethod
    async def list_unclosed(self, installation_id: UUID) -> tuple[BrowserSessionRecord, ...]:
        raise NotImplementedError

    @abstractmethod
    async def mutate(self, operation_id: UUID, expected_version: int,
                     mutation: BrowserSessionMutation) -> BrowserSessionRecord:
        raise NotImplementedError

    @abstractmethod
    async def summarize(self, installation_id: UUID) -> BrowserLedgerCounts:
        raise NotImplementedError
