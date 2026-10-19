# File: backend/app/domain/exceptions/task_errors.py
"""Domain and application exceptions for standalone task execution and control."""

from app.domain.exceptions.domain_exceptions import DomainError


class TaskBusyError(DomainError):
    """Raised when execution slot is already occupied (409 Conflict with zero effects)."""


class StaleVersionError(DomainError):
    """Raised when an aggregate version does not match expected_version (optimistic lock)."""


class TaskNotRetriableError(DomainError):
    """Raised when attempting to retry a task not in FAILED status."""


class IdempotencyConflictError(DomainError):
    """Raised when the same command_id is used with different payload or target."""


class ControlTargetNotFoundError(DomainError):
    """Raised when target of a control command does not exist or is not owned."""


class TaskAdmissionClosedError(DomainError):
    """Raised when admission is closed due to system shutdown."""


class TaskNotStartableError(DomainError):
    """Task state or submission evidence prohibits a new attempt."""


class StartOutcomeUnknownError(DomainError):
    """Admission settlement could not be confirmed safely."""


class LegacyCommandUnverifiedError(DomainError):
    """Historical command has no current execution authority."""


class ExecutionAuthorityError(DomainError):
    """The current account or attempt no longer authorizes provider work."""


class ReceiptOutcomeUnknownError(DomainError):
    """An admitted receipt write could not be confirmed."""
