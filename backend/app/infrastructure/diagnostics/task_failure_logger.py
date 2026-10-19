# File: backend/app/infrastructure/diagnostics/task_failure_logger.py
"""Log safe metadata only: never hand an exception object to a logging formatter."""
import json
import logging
from types import CodeType
from typing import Mapping

from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError, ProgrammingError, StatementError
from app.application.task_diagnostics import TaskFailureContext
from app.domain.exceptions.browser_errors import (
    BrowserError, BrowserUnavailable, BrowserCleanupPending, BrowserOwnershipError, BrowserLedgerConflict,
)
from app.domain.exceptions.mailbox_errors import MailboxError
from app.domain.exceptions.task_errors import ExecutionAuthorityError, StaleVersionError
from app.infrastructure.diagnostics.task_failure_frames import (
    SafeDiagnosticFrameLabel, safe_diagnostic_frame,
)

_ERROR_KINDS = (
    (ValueError, "VALUE_ERROR"), (TypeError, "TYPE_ERROR"),
    (AttributeError, "ATTRIBUTE_ERROR"), (RuntimeError, "RUNTIME_ERROR"),
    (TimeoutError, "TIMEOUT_ERROR"), (KeyError, "KEY_ERROR"),
    (MailboxError, "MAILBOX_ERROR"), (BrowserError, "BROWSER_ERROR"),
    (BrowserUnavailable, "BROWSER_UNAVAILABLE"), (BrowserCleanupPending, "BROWSER_CLEANUP_PENDING"),
    (BrowserOwnershipError, "BROWSER_OWNERSHIP_ERROR"), (BrowserLedgerConflict, "BROWSER_LEDGER_CONFLICT"),
    (ExecutionAuthorityError, "EXECUTION_AUTHORITY_ERROR"), (StaleVersionError, "STALE_VERSION_ERROR"),
    (DBAPIError, "DATABASE_API_ERROR"), (IntegrityError, "DATABASE_INTEGRITY_ERROR"),
    (OperationalError, "DATABASE_OPERATIONAL_ERROR"), (ProgrammingError, "DATABASE_PROGRAMMING_ERROR"),
    (StatementError, "DATABASE_STATEMENT_ERROR"),
)


class LoggingTaskFailureDiagnostics:
    def __init__(self, logger: logging.Logger,
                 *, trusted_frames: Mapping[CodeType, SafeDiagnosticFrameLabel]):
        self._logger = logger
        self._frames = tuple(trusted_frames.items())

    def record_failure(self, context: TaskFailureContext, error: Exception) -> None:
        event = {
            "event": "TASK_EXECUTION_FAILURE", "task_id": str(context.task_id),
            "attempt_id": str(context.attempt_id), "command_id": str(context.command_id),
            "stage": context.stage.value, "code": context.code.value, "reason": context.reason,
            "exceptions": self._exception_nodes(error),
        }
        # All values are fixed labels, validated context, or bounded numeric locations.
        message = json.dumps(event, ensure_ascii=True, separators=(",", ":"))
        if len(message.encode("utf-8")) > 8192:
            event["exceptions"] = []
            message = json.dumps(event, ensure_ascii=True, separators=(",", ":"))
        self._logger.error("%s", message)

    def _exception_nodes(self, error: Exception) -> list[dict]:
        nodes, seen = [], set()
        for _ in range(2):
            if error is None or id(error) in seen:
                break
            seen.add(id(error))
            kind = next((label for known, label in _ERROR_KINDS if type(error) is known),
                        "UNEXPECTED_EXCEPTION")
            frames, cursor = [], error.__traceback__
            # Bound traversal as well as output, including adversarial long stacks.
            for _ in range(32):
                if cursor is None:
                    break
                frames.append(safe_diagnostic_frame(cursor.tb_frame, cursor.tb_lineno,
                                                     dict(self._frames)))
                cursor = cursor.tb_next
            nodes.append({"kind": kind, "frames": frames[-8:]})
            error = error.__cause__ if error.__cause__ is not None else error.__context__
        return nodes
