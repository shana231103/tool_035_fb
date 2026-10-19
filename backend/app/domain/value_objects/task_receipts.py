# File: backend/app/domain/value_objects/task_receipts.py
"""Versioned immutable command receipts; legacy records never confer authority."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Union
from uuid import UUID
from app.domain.value_objects.operator_identity import ControlTargetKind


class StartOutcome(str, Enum):
    ADMITTED = "ADMITTED"
    RUNNING = "RUNNING"
    DRAINING = "DRAINING"
    FINISHED = "FINISHED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


class LegacySlotOutcome(str, Enum):
    FREE = "FREE"
    ADMITTED = "ADMITTED"
    RUNNING = "RUNNING"
    DRAINING = "DRAINING"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


class ControlReceiptStatus(str, Enum):
    ADMITTED = "ADMITTED"
    COMPLETE = "COMPLETE"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


@dataclass(frozen=True)
class _StartIdentity:
    operator_id: UUID
    command_id: UUID
    task_id: UUID
    attempt_id: UUID
    slot_generation: int
    run_version: int
    runtime_epoch: UUID
    admitted_task_version: int
    admitted_at: datetime
    payload_fingerprint: str


@dataclass(frozen=True)
class CurrentStartReceiptRecord(_StartIdentity):
    outcome_phase: StartOutcome = StartOutcome.ADMITTED
    is_historical: bool = False
    authority_contract_version: int = field(default=2, init=False)

    def __post_init__(self):
        object.__setattr__(self, "outcome_phase", StartOutcome(self.outcome_phase))
        if min(self.slot_generation, self.run_version) < 1 or self.admitted_task_version < 2:
            raise ValueError("Invalid current admission identity.")
        if len(self.payload_fingerprint) != 64:
            raise ValueError("Current admission requires a SHA256 fingerprint.")


@dataclass(frozen=True)
class LegacyStartReceiptRecord(_StartIdentity):
    outcome_phase: LegacySlotOutcome = LegacySlotOutcome.ADMITTED
    is_historical: bool = field(default=True, init=False)
    authority_contract_version: int = field(default=1, init=False)

    def __post_init__(self):
        object.__setattr__(self, "outcome_phase", LegacySlotOutcome(self.outcome_phase))


StartReceiptRecord = Union[CurrentStartReceiptRecord, LegacyStartReceiptRecord]


@dataclass(frozen=True)
class ControlReceipt:
    command_id: UUID
    operator_id: UUID
    target_kind: ControlTargetKind
    target_id: str
    target_generation: int
    initiating_session_id: UUID
    auth_version: int
    admitted_at: datetime
    status: ControlReceiptStatus = ControlReceiptStatus.ADMITTED
    result_code: str = "ADMITTED"
    completed_at: Optional[datetime] = None
    version: int = 1
    authority_contract_version: int = 2
    payload_fingerprint: Optional[str] = None
    expected_task_version: Optional[int] = None
    attempt_id: Optional[UUID] = None

    def __post_init__(self):
        if self.authority_contract_version not in (1, 2) or self.version < 1:
            raise ValueError("Invalid control authority version.")
        if self.authority_contract_version == 2 and self.target_kind == ControlTargetKind.STOP_TASK:
            if not self.payload_fingerprint or not self.expected_task_version or self.expected_task_version < 1:
                raise ValueError("Current Stop requires a fingerprint and expected task version.")
