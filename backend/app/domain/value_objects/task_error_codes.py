# File: backend/app/domain/value_objects/task_error_codes.py
"""Finite public task errors and state-aware projection without provider text."""

from enum import Enum

from app.domain.value_objects.enums import TaskStatus


class TaskErrorCode(str, Enum):
    EXECUTION_FAILED = "EXECUTION_FAILED"
    EXECUTION_NOT_READY = "EXECUTION_NOT_READY"
    SUBMIT_UNKNOWN = "SUBMIT_UNKNOWN"
    OPERATOR_CANCELLED = "OPERATOR_CANCELLED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    FORM_INVALID = "FORM_INVALID"
    MAILBOX_NOT_READY = "MAILBOX_NOT_READY"
    BROWSER_NOT_READY = "BROWSER_NOT_READY"
    EXECUTION_FENCE_FAILED = "EXECUTION_FENCE_FAILED"


_PUBLIC_CODES = frozenset(code.value for code in TaskErrorCode)


def public_task_error_code(
    status: TaskStatus | str,
    candidate: str | None,
    *,
    has_submission_evidence: bool = False,
) -> str | None:
    """Return a canonical code; evidence takes priority over failure history.

    This is a display policy only. It never grants retry or changes persisted
    history, and applying it again to a projected code preserves the result.
    """
    if not isinstance(status, str) or status not in (
        TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.NEEDS_REVIEW,
    ):
        return None
    code = (candidate.value if isinstance(candidate, TaskErrorCode)
            else candidate if isinstance(candidate, str) else None)
    if code == "EXECUTION_INTERRUPTED":
        code = TaskErrorCode.EXECUTION_FAILED.value
    if code not in _PUBLIC_CODES:
        code = None

    if status == TaskStatus.NEEDS_REVIEW or has_submission_evidence:
        return (TaskErrorCode.RECOVERY_REQUIRED.value
                if code == TaskErrorCode.RECOVERY_REQUIRED
                else TaskErrorCode.SUBMIT_UNKNOWN.value)
    if status == TaskStatus.FAILED:
        return code or TaskErrorCode.EXECUTION_FAILED.value
    if code == TaskErrorCode.OPERATOR_CANCELLED or (
        isinstance(candidate, str) and candidate == "STOP_REQUESTED"
    ):
        return TaskErrorCode.OPERATOR_CANCELLED.value
    return None
