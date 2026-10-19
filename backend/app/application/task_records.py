# File: backend/app/application/task_records.py
"""Commands and view records for standalone task creation, admission, and control."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Tuple
from uuid import UUID

from app.application.task_queries import TaskReadModel
from app.domain.value_objects.enums import ProxyCountry, TaskStatus
from app.domain.value_objects.task_execution import ControlReceiptStatus, SlotPhase


@dataclass(frozen=True)
class EvidenceInput:
    filename: str
    content: bytes
    content_type: str = "image/png"


@dataclass(frozen=True)
class CreateTaskCommand:
    name: str
    target_urls: Tuple[str, ...]
    original_url: str
    explanation: str
    owner_profile_id: UUID
    preferred_country: Optional[ProxyCountry] = None


@dataclass(frozen=True)
class StartTaskCommand:
    command_id: UUID
    task_id: UUID
    expected_version: int

    def __post_init__(self):
        if self.expected_version < 1:
            raise ValueError("Expected version must be positive.")


@dataclass(frozen=True)
class RetryTaskCommand:
    task_id: UUID
    expected_version: int
    command_id: Optional[UUID] = None

    def __post_init__(self):
        if self.expected_version < 1:
            raise ValueError("Expected version must be positive.")


@dataclass(frozen=True)
class StopTaskCommand:
    command_id: UUID
    task_id: UUID
    expected_version: int
    attempt_id: Optional[UUID] = None
    reason: str = "operator_requested"

    def __post_init__(self):
        if self.expected_version < 1 or self.reason != "operator_requested":
            raise ValueError("Invalid Stop command.")


@dataclass(frozen=True)
class DisconnectCommand:
    command_id: UUID
    connection_id: str
    reason: str = "operator_disconnect"


@dataclass(frozen=True)
class TaskView:
    id: UUID
    operator_id: UUID
    name: str
    status: TaskStatus
    version: int
    target_urls: Tuple[str, ...]
    target_count: int
    original_url: str
    explanation: str
    owner_profile_id: UUID
    preferred_country: Optional[ProxyCountry]
    retry_count: int
    max_retries: int
    created_at: datetime
    updated_at: datetime
    attempt_id: Optional[UUID] = None
    completed_at: Optional[datetime] = None
    meta_case_number: Optional[str] = None
    receipt_text: Optional[str] = None
    screenshot_path: Optional[str] = None
    error_message: Optional[str] = None
    safe_error_code: Optional[str] = None
    submitted_at: Optional[datetime] = None
    can_retry: bool = False
    has_submission_evidence: bool = False
    legacy_read_only: bool = False


@dataclass(frozen=True)
class TaskPage:
    items: Tuple[TaskReadModel, ...]
    limit: int
    offset: int
    has_more: bool


@dataclass(frozen=True)
class ExecutionAvailability:
    available: bool
    current_phase: SlotPhase
    generation: int
    blocking_recovery: bool


@dataclass(frozen=True)
class ControlView:
    command_id: UUID
    status: ControlReceiptStatus
    result_code: str
    target_id: str
    admitted_at: datetime
    completed_at: Optional[datetime] = None
