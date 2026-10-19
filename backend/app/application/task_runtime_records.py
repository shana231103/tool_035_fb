# File: backend/app/application/task_runtime_records.py
"""Private immutable records crossing execution lifetime boundaries."""
import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Awaitable, Callable
from uuid import UUID

from app.domain.ports.automation_driver import AutomationReceipt
from app.domain.value_objects.enums import TaskStatus
from app.domain.value_objects.task_execution import ExecutionGrant, RuntimeDrainProof
from app.domain.exceptions.task_errors import StartOutcomeUnknownError

Deadline = float
if TYPE_CHECKING:
    from app.application.owned_tasks import OwnedTasks


class OwnedWorkKind(str, Enum):
    ADMISSION = "ADMISSION"
    CONTROL = "CONTROL"
    WORKFLOW = "WORKFLOW"
    COLLECTOR = "COLLECTOR"
    PROVIDER_HANDOFF = "PROVIDER_HANDOFF"
    CLEANUP = "CLEANUP"
    RECEIPT = "RECEIPT"
    FINALIZER = "FINALIZER"


class CommitResolution(str, Enum):
    CONFIRMED_COMMIT = "CONFIRMED_COMMIT"
    CONFIRMED_ABSENT = "CONFIRMED_ABSENT"
    UNKNOWN = "UNKNOWN"


class ReleaseResolution(str, Enum):
    CONFIRMED_RELEASE = "CONFIRMED_RELEASE"
    NOT_RELEASED = "NOT_RELEASED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class AdmissionToken:
    id: UUID
    runtime_epoch: UUID


@dataclass(frozen=True)
class OwnedTicket:
    id: UUID
    runtime_epoch: UUID
    attempt_id: UUID | None


@dataclass(frozen=True)
class OwnedCensus:
    census_id: UUID
    runtime_epoch: UUID
    attempt_id: UUID | None
    registration_closed: bool
    active_counts: tuple[tuple[OwnedWorkKind, int], ...]
    callbacks_settled: bool
    complete: bool

    @property
    def remaining(self) -> int:
        return sum(count for _, count in self.active_counts)


@dataclass(frozen=True)
class RuntimeSnapshot:
    runtime_epoch: UUID
    admission_open: bool
    busy: bool
    retained_blocked: bool
    phase: str
    grant: ExecutionGrant | None = field(default=None, repr=False)


@dataclass(frozen=True)
class DrainOutcome:
    state: str
    safe_code: str
    proof: RuntimeDrainProof | None = None


@dataclass(frozen=True)
class SafeProgress:
    stage: str = ""
    safe_code: str | None = None
    completed: int = 0
    total: int = 0

    def __post_init__(self):
        if len(self.stage) > 64 or (self.safe_code and len(self.safe_code) > 64):
            raise ValueError("INPUT_INVALID")
        if not 0 <= self.completed <= 10000 or not 0 <= self.total <= 10000:
            raise ValueError("INPUT_INVALID")


@dataclass(frozen=True)
class ExecutionOutcome:
    status: TaskStatus
    safe_code: str | None = None
    receipt: AutomationReceipt | None = None
    screenshot_path: str | None = None


ProgressSink = Callable[[TaskStatus, SafeProgress], Awaitable[None]]
ReceiptSink = Callable[[AutomationReceipt], Awaitable[None]]


@dataclass
class StagedHandle:
    token: AdmissionToken
    grant: ExecutionGrant
    gate: asyncio.Event
    registry: "OwnedTasks"
    task: asyncio.Task[None] | None = None
    ticket: OwnedTicket | None = None
    state: str = "STAGED"
    safe_code: str | None = None
    stop_requested: bool = False


