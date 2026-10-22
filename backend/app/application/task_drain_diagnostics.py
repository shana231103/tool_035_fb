"""Bounded, fail-open drain diagnostics; never serialize exception text or objects."""
import asyncio
from contextlib import contextmanager
from enum import Enum
import json
import logging
import math
from uuid import UUID

from app.domain.exceptions import browser_errors, task_errors

logger = logging.getLogger("uvicorn.error.task_drain_diagnostics")
_STAGES = frozenset("""RUNTIME_RUN RUNTIME_BLOCKED RUNTIME_SHUTDOWN_BEGIN RUNTIME_SHUTDOWN_WAIT
RUNTIME_SHUTDOWN_RETAINED SHUTDOWN_CREATOR SHUTDOWN_OPERATIONS SHUTDOWN_CONTROLS
SHUTDOWN_RUNTIME SHUTDOWN_RUNTIME_CHECK SHUTDOWN_MAILBOX_SESSIONS SHUTDOWN_AUTHORIZER
SHUTDOWN_TASK_SERVICES SHUTDOWN_MAILBOX_CONNECTIONS SHUTDOWN_SOCKET SHUTDOWN_STORAGE
SHUTDOWN_GRAPH SHUTDOWN_BROWSER SHUTDOWN_DATABASE
DRAIN_SCOPE_EXIT DRAIN_PHASE_WRITE DRAIN_RECEIPT_WRITE DRAIN_COMMIT DRAIN_CENSUS
DRAIN_RESOURCE_CHECK DRAIN_PROOF_SCOPE_EXIT DRAIN_PROOF_AUTHORITY DRAIN_PROOF_LEDGER
DRAIN_PROOF_VALIDATE DRAIN_PROOF_CREATE RELEASE_SCOPE_EXIT RELEASE_SLOT_WRITE
RELEASE_RECEIPT_WRITE RELEASE_COMMIT RELEASE_READ_SCOPE_EXIT RELEASE_READ_SLOT
RELEASE_READ_RECEIPT RELEASE_READBACK RECOVERY_SCOPE_EXIT RECOVERY_READ_SLOT
RECOVERY_MARK RECOVERY_READ_RECEIPT RECOVERY_RECEIPT_WRITE RECOVERY_COMMIT
""".split())
_BOOLS = frozenset("""census_complete registration_closed callbacks_settled ledger_complete
business_finalized authority_match runtime_busy runtime_blocked workflow_done""".split())
_NUMBERS = frozenset("owned_remaining charged_count unclosed_count remaining_ms".split())
_LABELS = {
    "result": frozenset("BEGIN COMPLETE ERROR INCOMPLETE".split()),
    "slot_phase": frozenset("FREE ADMITTED RUNNING DRAINING RECOVERY_REQUIRED".split()),
    "task_status": frozenset("DRAFT PREPARING PENDING QUEUED RUNNING WAITING_EMAIL_SLOT WAITING_EMAIL_CODE VERIFYING_EMAIL SUBMITTING NEEDS_REVIEW SUBMITTED FAILED CANCELLED".split()),
    "runtime_phase": frozenset("FREE STAGED BLOCKED ABORTED ACTIVATING ACTIVE DRAINING RELEASED".split()),
    "resolution": frozenset("CONFIRMED_RELEASE NOT_RELEASED UNKNOWN RELEASED RECOVERY_REQUIRED FINISHED".split()),
    "recovery_reason": frozenset("START_OUTCOME_UNKNOWN EXECUTION_RECOVERY_REQUIRED SHUTDOWN_DRAIN_UNKNOWN RESOURCE_DRAIN_UNKNOWN OWNED_DRAIN_UNKNOWN RELEASE_OUTCOME_UNKNOWN".split()),
}
_SQLSTATES = frozenset("08000 08001 08003 08004 08006 08007 08P01 0A000 23502 23503 23505 23514 25006 25P02 3D000 3F000 40001 40P01 42501 42601 42P01 42703 42883 53300 53400 55P03 57014 57P01 57P02 57P03 58000 XX000".split())
_ERROR_KINDS = {
    ValueError: "VALUE_ERROR", RuntimeError: "RUNTIME_ERROR", TypeError: "TYPE_ERROR",
    AttributeError: "ATTRIBUTE_ERROR", KeyError: "KEY_ERROR", TimeoutError: "TIMEOUT",
    OSError: "OS_ERROR", asyncio.CancelledError: "CANCELLED",
    task_errors.StaleVersionError: "STALE_VERSION",
    task_errors.ExecutionAuthorityError: "AUTHORITY_ERROR",
    browser_errors.BrowserError: "BROWSER_ERROR",
    browser_errors.BrowserUnavailable: "BROWSER_UNAVAILABLE",
    browser_errors.BrowserCleanupPending: "BROWSER_CLEANUP_PENDING",
    browser_errors.BrowserOwnershipError: "BROWSER_OWNERSHIP_ERROR",
    browser_errors.BrowserLedgerConflict: "BROWSER_LEDGER_CONFLICT",
}
_QUALIFIED_ERRORS = {("sqlalchemy.exc", name): label for name, label in (
    ("DBAPIError", "DBAPI_ERROR"), ("OperationalError", "DB_OPERATIONAL_ERROR"),
    ("IntegrityError", "DB_INTEGRITY_ERROR"), ("InterfaceError", "DB_INTERFACE_ERROR"),
    ("ProgrammingError", "DB_PROGRAMMING_ERROR"), ("StatementError", "DB_STATEMENT_ERROR"),
    ("InternalError", "DB_INTERNAL_ERROR"), ("TimeoutError", "DB_POOL_TIMEOUT"))}


def _error_kind(error):
    kind = type(error)
    return _ERROR_KINDS.get(kind, _QUALIFIED_ERRORS.get((kind.__module__, kind.__name__), "OTHER"))


def _error_fields(error):
    fields = {"error_kind": _error_kind(error)}
    seen = set()
    for depth in range(3):
        if error is None or id(error) in seen:
            break
        seen.add(id(error))
        if depth:
            fields.setdefault("cause_kind", _error_kind(error))
        for key in ("sqlstate", "pgcode"):
            state = getattr(error, key, None)
            if type(state) is str and state in _SQLSTATES:
                fields.setdefault("sqlstate", state)
        error = (getattr(error, "orig", None) or getattr(error, "__cause__", None)
                 or getattr(error, "__context__", None))
    return fields


def _observations(details):
    """Inspect only known snapshot fields inside emit_drain's fail-open boundary."""
    census = details.pop("census", None)
    if census is not None:
        details.update(census_complete=census.complete, registration_closed=census.registration_closed,
                       callbacks_settled=census.callbacks_settled, owned_remaining=census.remaining)
    ledger = details.pop("ledger", None)
    if ledger is not None:
        details.update(ledger_complete=ledger.complete, charged_count=ledger.total_charged,
                       unclosed_count=len(ledger.unclosed_records))
    task = details.pop("task", None)
    if task is not None:
        details["task_status"] = task.status.value
    return details


def emit_drain(stage: str, *, grant=None, error=None, **details) -> None:
    """Emit a single <=4096-byte JSON event. Invalid or failing diagnostics are dropped."""
    try:
        if type(stage) is not str or stage not in _STAGES:
            return
        event = {"event": "TASK_DRAIN_DIAGNOSTIC", "stage": stage}
        if grant is not None:
            identities = {"owner_id": grant.scope.operator_id, "task_id": grant.scope.task_id,
                          "attempt_id": grant.attempt_id, "command_id": grant.command_id,
                          "runtime_epoch": grant.runtime_epoch}
            event.update({key: str(value) for key, value in identities.items() if type(value) is UUID})
        for key, value in _observations(details).items():
            if key in _LABELS and isinstance(value, Enum):
                value = value.value
            if key in _BOOLS and type(value) is bool:
                event[key] = value
            elif key in _NUMBERS and type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 10**12:
                event[key] = value
            elif key in _LABELS and type(value) is str and value in _LABELS[key]:
                event[key] = value
        if error is not None:
            event.update(_error_fields(error))
        message = json.dumps(event, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
        if len(message) <= 4096:
            logger.info(message)
    except BaseException:
        pass  # Diagnostic logging, including a broken sink, cannot alter drain/cancellation.


@contextmanager
def drain_stage(stage: str, grant=None):
    """Observe existing scopes/awaits, preserving every exception including cancellation."""
    emit_drain(stage, grant=grant, result="BEGIN")
    try:
        yield
    except BaseException as error:
        emit_drain(stage, grant=grant, error=error, result="ERROR")
        raise
    else:
        emit_drain(stage, grant=grant, result="COMPLETE")
