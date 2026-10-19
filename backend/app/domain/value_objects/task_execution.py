# File: backend/app/domain/value_objects/task_execution.py
"""Immutable domain value objects and records for standalone task execution and control."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID
from app.domain.value_objects.operator_identity import ControlTargetKind

from app.domain.value_objects.task_receipts import (
    ControlReceipt, ControlReceiptStatus, CurrentStartReceiptRecord,
    LegacyStartReceiptRecord, LegacySlotOutcome, StartOutcome, StartReceiptRecord,
)


class SlotPhase(str, Enum):
    FREE = "FREE"
    ADMITTED = "ADMITTED"
    RUNNING = "RUNNING"
    DRAINING = "DRAINING"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


@dataclass(frozen=True)
class ExecutionScope:
    operator_id: UUID
    task_id: UUID
    attempt_id: UUID
    run_version: int
    slot_generation: int
    runtime_epoch: UUID

    def __post_init__(self):
        if min(self.run_version, self.slot_generation) < 1:
            raise ValueError("Execution scope requires positive authority versions.")
        if not all(isinstance(v, UUID) and v.int for v in (self.operator_id, self.task_id, self.attempt_id, self.runtime_epoch)):
            raise ValueError("Execution scope requires UUID identities.")


@dataclass(frozen=True)
class ExecutionGrant:
    scope: ExecutionScope
    admission_id: UUID
    admitted_at: datetime
    observed_task_version: int

    def __post_init__(self):
        if self.observed_task_version < 1 or not isinstance(self.admission_id, UUID) or not self.admission_id.int:
            raise ValueError("Invalid execution grant.")
        if self.admitted_at.tzinfo is None:
            raise ValueError("Admission time requires a timezone.")

    @property
    def attempt_id(self) -> UUID:
        return self.scope.attempt_id

    @property
    def run_version(self) -> int:
        return self.scope.run_version

    @property
    def slot_generation(self) -> int:
        return self.scope.slot_generation

    @property
    def command_id(self) -> UUID:
        return self.admission_id

    @property
    def runtime_epoch(self) -> UUID:
        return self.scope.runtime_epoch


@dataclass(frozen=True)
class RuntimeDrainProof:
    task_id: UUID
    attempt_id: UUID
    slot_generation: int
    runtime_epoch: UUID
    owner_id: UUID
    command_id: UUID
    census_id: UUID
    registration_closed: bool
    owned_remaining: int
    callbacks_settled: bool
    business_finalized: bool
    ledger_complete: bool
    ledger_clear: bool
    observed_at: datetime


@dataclass(frozen=True)
class SystemRecoveryProof:
    recovery_id: UUID
    generation: int
    runtime_epoch: UUID
    prior_active_census_complete: bool
    prior_active_census_count: int
    ledger_clear: bool
    installation_id: UUID
    provider_binding_id: UUID
    census_id: UUID
    ledger_complete: bool


@dataclass(frozen=True)
class ExecutionSlotRecord:
    singleton_id: int = 1
    generation: int = 0
    phase: SlotPhase = SlotPhase.FREE
    grant: Optional[ExecutionGrant] = None
    recovery_id: Optional[UUID] = None
    recovery_reason: Optional[str] = None
    recovery_started_at: Optional[datetime] = None
    authority_contract_version: int = 2

    @property
    def is_free(self) -> bool:
        return self.phase == SlotPhase.FREE and self.grant is None and self.recovery_id is None

    @property
    def is_busy(self) -> bool:
        return not self.is_free

    @property
    def task_id(self) -> Optional[UUID]:
        return self.grant.scope.task_id if self.grant else None

    @property
    def attempt_id(self) -> Optional[UUID]:
        return self.grant.attempt_id if self.grant else None

    @property
    def operator_account_id(self) -> Optional[UUID]:
        return self.grant.scope.operator_id if self.grant else None

    @property
    def run_version(self) -> Optional[int]:
        return self.grant.run_version if self.grant else None

    @property
    def runtime_epoch(self) -> Optional[UUID]:
        return self.grant.runtime_epoch if self.grant else None

    @property
    def command_id(self) -> Optional[UUID]:
        return self.grant.command_id if self.grant else None


