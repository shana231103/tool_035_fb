# File: backend/app/presentation/task_http_errors.py
"""Translate task failures without projecting exception/provider text."""

from fastapi import HTTPException
from app.domain.exceptions.domain_exceptions import (
    EntityNotFoundError, InvalidStateTransitionError,
)
from app.domain.exceptions.operator_errors import (
    AccountDisabledError, OperatorError, OwnedResourceNotFoundError,
    SessionExpiredError, SessionRevokedError,
)
from app.domain.exceptions.task_errors import (
    ControlTargetNotFoundError, IdempotencyConflictError, StaleVersionError,
    TaskAdmissionClosedError, TaskBusyError, TaskNotRetriableError,
    ExecutionAuthorityError, LegacyCommandUnverifiedError,
    ReceiptOutcomeUnknownError, StartOutcomeUnknownError, TaskNotStartableError,
)


def task_http_error(error: Exception) -> HTTPException:
    mapping = (
        ((EntityNotFoundError, OwnedResourceNotFoundError,
          ControlTargetNotFoundError), 404, "NOT_FOUND"),
        ((SessionExpiredError, SessionRevokedError), 401, "SESSION_INVALID"),
        ((AccountDisabledError,), 403, "ACCOUNT_DISABLED"),
        ((TaskBusyError,), 409, "EXECUTION_BUSY"),
        ((StaleVersionError,), 409, "TASK_VERSION_CONFLICT"),
        ((IdempotencyConflictError,), 409, "COMMAND_REUSE_CONFLICT"),
        ((TaskNotRetriableError,), 409, "TASK_NOT_RETRIABLE"),
        ((TaskNotStartableError,), 409, "TASK_NOT_STARTABLE"),
        ((LegacyCommandUnverifiedError,), 409, "LEGACY_COMMAND_UNVERIFIED"),
        ((ExecutionAuthorityError,), 409, "EXECUTION_AUTHORITY_INVALID"),
        ((ReceiptOutcomeUnknownError,), 503, "RECEIPT_OUTCOME_UNKNOWN"),
        ((StartOutcomeUnknownError,), 503, "START_OUTCOME_UNKNOWN"),
        ((InvalidStateTransitionError,), 409, "TASK_NOT_STARTABLE"),
        ((TaskAdmissionClosedError,), 503, "EXECUTION_UNAVAILABLE"),
        ((OperatorError,), 409, "EXECUTION_NOT_READY"),
    )
    for types, status, code in mapping:
        if isinstance(error, types):
            return HTTPException(status, detail={"code": code, "message": code})
    return HTTPException(503, detail={"code": "START_OUTCOME_UNKNOWN",
                                     "message": "Check the command status."})
