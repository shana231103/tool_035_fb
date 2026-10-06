# File: backend/app/domain/events/domain_events.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import UUID


@dataclass(frozen=True)
class DomainEvent:
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass(frozen=True)
class TaskStartedEvent(DomainEvent):
    job_id: UUID
    task_id: UUID
    target_url: str
    proxy_id: Optional[UUID] = None


@dataclass(frozen=True)
class TaskSubmittedEvent(DomainEvent):
    job_id: UUID
    task_id: UUID
    meta_case_number: Optional[str]
    screenshot_path: Optional[str]


@dataclass(frozen=True)
class TaskFailedEvent(DomainEvent):
    job_id: UUID
    task_id: UUID
    error_message: str
    retryable: bool
    retry_count: int


@dataclass(frozen=True)
class JobStatusChangedEvent(DomainEvent):
    job_id: UUID
    old_status: str
    new_status: str
