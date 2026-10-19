# File: backend/app/application/task_failure_policy.py
"""Classify known failures without exporting exception text or changing eligibility."""
from app.application.task_diagnostics import TaskFailureClassification, TaskStage
from app.domain.exceptions.browser_errors import (
    BrowserError, BrowserUnavailable, BrowserCleanupPending, BrowserOwnershipError,
    BrowserLedgerConflict, SAFE_BROWSER_REASONS,
)
from app.domain.exceptions.mailbox_errors import MailboxError, SAFE_MAILBOX_REASONS
from app.domain.exceptions.task_errors import ExecutionAuthorityError, StaleVersionError
from app.domain.value_objects.task_error_codes import TaskErrorCode as Code

_BROWSER_TYPES = (BrowserError, BrowserUnavailable, BrowserCleanupPending,
                  BrowserOwnershipError, BrowserLedgerConflict)
_RECOVERY_REASONS = frozenset({
    "BROWSER_AUTHORITY_MISMATCH", "BROWSER_INSTANCE_ACTIVE", "PROVIDER_BINDING_MISMATCH",
    "BROWSER_CREATE_UNKNOWN", "BROWSER_CLEANUP_PENDING", "BROWSER_LEDGER_UNCERTAIN",
    "BROWSER_LEDGER_CONFLICT", "BROWSER_RECEIPT_PERSISTENCE_UNCERTAIN",
})
_AUTHORITY_REASONS = frozenset({
    "EXECUTION_AUTHORITY_REVOKED", "EXECUTION_GRANT_MISMATCH", "TASK_VERSION_CONFLICT",
})


def classify_task_failure(stage: TaskStage, error: Exception) -> TaskFailureClassification:
    error_type = type(error)
    if error_type is MailboxError:
        reason = error.reason
        reason = reason if type(reason) is str and reason in SAFE_MAILBOX_REASONS else None
        return TaskFailureClassification(Code.MAILBOX_NOT_READY, reason)
    if any(error_type is known for known in _BROWSER_TYPES):
        reason = error.reason
        reason = reason if type(reason) is str and reason in SAFE_BROWSER_REASONS else None
        code = Code.RECOVERY_REQUIRED if reason in _RECOVERY_REASONS else Code.BROWSER_NOT_READY
        return TaskFailureClassification(code, reason)
    if error_type is ExecutionAuthorityError or error_type is StaleVersionError:
        args = error.args
        reason = args[0] if len(args) == 1 and type(args[0]) is str else None
        reason = reason if reason in _AUTHORITY_REASONS else None
        return TaskFailureClassification(Code.EXECUTION_FENCE_FAILED, reason)
    if error_type is TimeoutError and stage is TaskStage.PREPARATION_BUDGET:
        return TaskFailureClassification(Code.EXECUTION_NOT_READY, "PREPARATION_TIMEOUT")
    if error_type is ValueError and stage in (TaskStage.PROFILE, TaskStage.INPUTS):
        return TaskFailureClassification(Code.FORM_INVALID)
    return TaskFailureClassification(Code.EXECUTION_FAILED)
