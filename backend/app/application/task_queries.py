# File: backend/app/application/task_queries.py
"""Read-only query port and projection models for standalone report tasks and legacy archive."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple
from uuid import UUID

from app.domain.value_objects.enums import ProxyCountry, TaskStatus


@dataclass(frozen=True)
class TaskReadModel:
    id: UUID
    operator_id: UUID
    name: str
    owner_profile_id: Optional[UUID]
    preferred_country: Optional[ProxyCountry]
    target_urls: Tuple[str, ...]
    target_count: int
    original_url: Optional[str]
    explanation: Optional[str]
    status: TaskStatus
    version: int
    attempt_id: Optional[UUID]
    retry_count: int
    max_retries: int
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    meta_case_number: Optional[str] = None
    receipt_text: Optional[str] = None
    screenshot_path: Optional[str] = None
    error_message: Optional[str] = None
    legacy_read_only: bool = False
    display_summary: Optional[str] = None
    submitted_at: Optional[datetime] = None
    has_submission_evidence: bool = False
    safe_error_code: Optional[str] = None
    can_start: bool = False
    can_retry: bool = False
    can_stop: bool = False


class ITaskQueries(ABC):
    """Read-only task query port bound to the current operator."""

    @abstractmethod
    async def list_tasks(
        self,
        limit: int,
        offset: int,
        statuses: Tuple[TaskStatus, ...] = (),
    ) -> Tuple[TaskReadModel, ...]:
        pass

    @abstractmethod
    async def get_detail(self, task_id: UUID) -> Optional[TaskReadModel]:
        pass
