# File: backend/app/domain/ports/task_execution_ports.py
"""Domain ports for task execution slot, start receipts, and operator controls."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional
from uuid import UUID

from app.domain.value_objects.task_execution import (
    ControlReceipt,
    ControlReceiptStatus,
    ExecutionGrant,
    ExecutionSlotRecord,
    RuntimeDrainProof,
    SlotPhase,
    StartReceiptRecord,
    StartOutcome,
    SystemRecoveryProof,
)


class ITaskExecutionRepository(ABC):
    """Authority repository managing the durable singleton execution slot."""

    @abstractmethod
    async def read(self) -> ExecutionSlotRecord:
        raise NotImplementedError

    @abstractmethod
    async def claim(
        self, grant: ExecutionGrant, expected_generation: int
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def set_phase(
        self,
        grant: ExecutionGrant,
        expected_phase: SlotPhase,
        next_phase: SlotPhase,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def mark_recovery(self, grant: Optional[ExecutionGrant], *, expected_generation: int, recovery_id: UUID, safe_code: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def release(
        self, grant: ExecutionGrant, proof: RuntimeDrainProof
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def clear_recovery(
        self,
        expected_generation: int,
        recovery_id: UUID,
        proof: SystemRecoveryProof,
    ) -> None:
        raise NotImplementedError


class ITaskStartReceiptRepository(ABC):
    """Owner-scoped durable command history for idempotent task start requests."""

    @abstractmethod
    async def get_owned(
        self, owner: UUID, command_id: UUID
    ) -> Optional[StartReceiptRecord]:
        raise NotImplementedError

    @abstractmethod
    async def insert(self, record: StartReceiptRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    async def set_outcome(
        self,
        owner: UUID,
        command_id: UUID,
        expected_phase: StartOutcome,
        next_phase: StartOutcome,
    ) -> None:
        raise NotImplementedError


class IControlRepository(ABC):
    """Owner-scoped durable receipt history for async controls (stop/disconnect)."""

    @abstractmethod
    async def get_owned(
        self, owner: UUID, id: UUID
    ) -> Optional[ControlReceipt]:
        raise NotImplementedError

    @abstractmethod
    async def insert(self, receipt: ControlReceipt) -> None:
        raise NotImplementedError

    @abstractmethod
    async def complete(self, owner: UUID, command_id: UUID, *, expected_version: int, result_code: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def mark_uncertain(self, owner: UUID, command_id: UUID, *, expected_version: int, reason: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def prune_completed(self, owner: UUID, before: datetime, limit: int) -> int:
        raise NotImplementedError
