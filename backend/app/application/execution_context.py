# File: backend/app/application/execution_context.py
from dataclasses import dataclass, field
from typing import Mapping
from uuid import UUID, uuid4

from app.domain.value_objects.bulk_import import ProfileSubmissionSnapshot
from app.domain.value_objects.mailbox_verification import MailboxBinding


@dataclass(frozen=True)
class DispatchPermit:
    id: UUID
    budget_incarnation: UUID
    task_id: UUID
    email: str | None


@dataclass(frozen=True)
class DrainConfirmed:
    task_id: UUID
    permit_id: UUID
    collector_joined: bool
    resource_clear: bool
    attempt_id: str | None = None


@dataclass(frozen=True)
class UnusedPermitConfirmed:
    permit_id: UUID
    task_id: UUID
    budget_incarnation: UUID
    claim_state: str = "NOT_APPLIED"
    no_registered_work: bool = True
    provider_not_entered: bool = True


@dataclass(frozen=True)
class DrainPending:
    task_id: UUID
    permit_id: UUID
    reason: str = "DRAIN_PENDING"
    attempt_id: str | None = None


@dataclass(frozen=True)
class RecoveredResourceHold:
    operation_id: UUID
    task_id: UUID
    attempt_id: str | None
    email: str | None


@dataclass(frozen=True)
class BudgetSnapshot:
    limit: int
    active_count: int
    held_count: int
    revision: int
    closed: bool
    identity_unknown: bool


@dataclass
class JobRunGate:
    job_id: UUID
    expected_profile_sha256: str | None = None
    id: UUID = field(default_factory=uuid4)
    closed: bool = False

    def close(self) -> None:
        self.closed = True


@dataclass
class ExecutionTrace:
    driver_entered: bool = False


@dataclass(frozen=True)
class AdmittedExecution:
    task_id: UUID
    attempt_id: str
    dispatch_revision: int
    profile: ProfileSubmissionSnapshot
    submission_email: str
    binding: MailboxBinding
    input_snapshot: Mapping[str, str]
    run_gate: JobRunGate
    trace: ExecutionTrace = field(default_factory=ExecutionTrace)


class AdmissionOutcomeUnknown(ValueError):
    def __init__(self, task_id: UUID, attempt_id: str):
        self.task_id, self.attempt_id = task_id, attempt_id
        super().__init__("ADMISSION_OUTCOME_UNKNOWN")
