# File: backend/app/application/task_diagnostics.py
"""Private, bounded diagnostic context owned by one execution coroutine."""
from dataclasses import dataclass
from enum import Enum
from typing import Protocol
from uuid import UUID

from app.domain.exceptions.browser_errors import SAFE_BROWSER_REASONS
from app.domain.exceptions.mailbox_errors import SAFE_MAILBOX_REASONS
from app.domain.value_objects.task_error_codes import TaskErrorCode
from app.domain.value_objects.task_execution import ExecutionGrant


class TaskStage(str, Enum):
    PREPARATION = "PREPARATION"
    AUTHORITY = "AUTHORITY"
    PROFILE = "PROFILE"
    INPUTS = "INPUTS"
    PROXY_SELECT = "PROXY_SELECT"
    READ_SCOPE_EXIT = "READ_SCOPE_EXIT"
    PREPARATION_BUDGET = "PREPARATION_BUDGET"
    PROXY_VALIDATE = "PROXY_VALIDATE"
    MAILBOX_BINDING = "MAILBOX_BINDING"
    MAILBOX_READY = "MAILBOX_READY"
    BROWSER_READY = "BROWSER_READY"
    BROWSER_RESOURCES = "BROWSER_RESOURCES"
    FREEZE_INPUT = "FREEZE_INPUT"
    BEGIN_ATTEMPT = "BEGIN_ATTEMPT"
    EXECUTE = "EXECUTE"
    FINALIZE = "FINALIZE"


_REASONS = SAFE_BROWSER_REASONS | SAFE_MAILBOX_REASONS | frozenset({
    "EXECUTION_AUTHORITY_REVOKED", "EXECUTION_GRANT_MISMATCH",
    "TASK_VERSION_CONFLICT", "INPUT_INVALID", "PREPARATION_TIMEOUT",
})


@dataclass(frozen=True)
class TaskFailureClassification:
    code: TaskErrorCode
    reason: str | None = None

    def __post_init__(self):
        if type(self.code) is not TaskErrorCode:
            raise ValueError("Invalid diagnostic code.")
        if self.reason is not None and (type(self.reason) is not str or self.reason not in _REASONS):
            raise ValueError("Invalid diagnostic reason.")


@dataclass(frozen=True)
class TaskFailureContext:
    task_id: UUID
    attempt_id: UUID
    command_id: UUID
    stage: TaskStage
    code: TaskErrorCode
    reason: str | None = None

    def __post_init__(self):
        if any(type(value) is not UUID or not value.int for value in (
            self.task_id, self.attempt_id, self.command_id,
        )) or type(self.stage) is not TaskStage:
            raise ValueError("Invalid diagnostic identity.")
        TaskFailureClassification(self.code, self.reason)


class ITaskFailureDiagnostics(Protocol):
    def record_failure(self, context: TaskFailureContext, error: Exception) -> None:
        """Emit only safe metadata; never retain or serialize the exception."""
        ...


class TaskAttemptTrace:
    def __init__(self, grant: ExecutionGrant):
        self._identity = (grant.scope.task_id, grant.attempt_id, grant.command_id)
        self._stage = TaskStage.PREPARATION

    @property
    def stage(self) -> TaskStage:
        return self._stage

    def enter(self, stage: TaskStage) -> None:
        if type(stage) is not TaskStage:
            raise ValueError("Invalid diagnostic stage.")
        self._stage = stage

    def failure_context(self, classification: TaskFailureClassification) -> TaskFailureContext:
        return TaskFailureContext(*self._identity, self._stage,
                                  classification.code, classification.reason)
