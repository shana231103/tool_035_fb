# File: backend/app/presentation/api/browser_status_dtos.py
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field
from app.domain.exceptions.browser_errors import safe_browser_reason


class TaskBrowserStatusDTO(BaseModel):
    task_id: UUID
    can_retry: bool
    resource_allows_retry: bool
    cleanup_state: Literal["CLEAR", "PENDING", "UNRESOLVED"]
    operation_refs: list[UUID]
    safe_reason: str | None = None


class BrowserStatusResponseDTO(BaseModel):
    state: Literal["READY", "DEGRADED", "BLOCKED", "STARTING", "CLOSED"]
    can_start: bool
    safe_reason: str | None = None
    charged: int = Field(ge=0)
    limit: int = Field(ge=0)
    pending: int = Field(ge=0)
    unknown: int = Field(ge=0)
    startup_classified: bool
    task: TaskBrowserStatusDTO | None = None

    @classmethod
    def from_view(cls, view):
        readiness = view.readiness
        task = view.task
        task_dto = None
        if task is not None:
            reason = task.retry_block_reason
            task_dto = TaskBrowserStatusDTO(task_id=task.task_id, can_retry=task.can_retry,
                resource_allows_retry=task.resource_allows_retry,
                cleanup_state=task.cleanup_state.value, operation_refs=list(task.operation_refs),
                safe_reason=reason if reason == "TASK_NOT_ELIGIBLE" else safe_browser_reason(reason))
        return cls(state=readiness.state.value, can_start=readiness.can_start,
            safe_reason=safe_browser_reason(readiness.safe_reason), charged=readiness.charged_count,
            limit=readiness.limit, pending=readiness.pending_count, unknown=readiness.unknown_count,
            startup_classified=readiness.startup_classified, task=task_dto)


class BrowserCleanupResponseDTO(BaseModel):
    operation_id: UUID
    state: Literal["CLOSED", "PENDING", "UNRESOLVED"]
    safe_reason: str | None = None

    @classmethod
    def from_outcome(cls, outcome):
        return cls(operation_id=outcome.operation_id, state=outcome.state.value,
            safe_reason=safe_browser_reason(outcome.reason))
