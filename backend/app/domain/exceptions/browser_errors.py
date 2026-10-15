# File: backend/app/domain/exceptions/browser_errors.py
from enum import Enum
from uuid import UUID


class RetryDisposition(str, Enum):
    NEVER = "NEVER"
    PRE_SUBMIT = "PRE_SUBMIT"
    OPERATOR = "OPERATOR"


SAFE_BROWSER_REASONS = frozenset({
    "BROWSER_NOT_CONFIGURED", "API_AUTH_REQUIRED", "API_INCOMPATIBLE",
    "BROWSER_AUTHORITY_MISMATCH", "BROWSER_INSTANCE_ACTIVE", "PROVIDER_BINDING_MISMATCH",
    "BROWSER_CAPACITY_WAIT", "API_RATE_LIMITED", "BROWSER_CREATE_UNKNOWN",
    "BROWSER_CLEANUP_PENDING", "BROWSER_LEDGER_UNCERTAIN", "BROWSER_LEDGER_CONFLICT",
    "BROWSER_CDP_UNREACHABLE", "BROWSER_ENDPOINT_REJECTED", "BROWSER_PROVIDER_UNAVAILABLE",
    "BROWSER_RECEIPT_PERSISTENCE_UNCERTAIN",
})


def safe_browser_reason(reason: str | None) -> str | None:
    if reason is None:
        return None
    return reason if reason in SAFE_BROWSER_REASONS else "BROWSER_PROVIDER_UNAVAILABLE"


class BrowserError(ValueError):
    """A safe code; never include provider bodies, credentials or endpoints."""

    def __init__(self, code: str = "BROWSER_PROVIDER_UNAVAILABLE",
                 disposition: RetryDisposition = RetryDisposition.NEVER,
                 operation_id: UUID | None = None):
        self.code = safe_browser_reason(code)
        self.reason = self.code
        self.disposition = RetryDisposition(disposition)
        self.operation_id = operation_id
        super().__init__(self.code)


class BrowserUnavailable(BrowserError):
    """Admission or provider capability is unavailable."""


class BrowserCleanupPending(BrowserError):
    def __init__(self, operation_id: UUID | None = None):
        super().__init__("BROWSER_CLEANUP_PENDING", RetryDisposition.OPERATOR, operation_id)


class BrowserOwnershipError(BrowserError):
    def __init__(self, code: str = "BROWSER_AUTHORITY_MISMATCH", operation_id: UUID | None = None):
        super().__init__(code, RetryDisposition.OPERATOR, operation_id)


class BrowserLedgerConflict(BrowserError):
    def __init__(self, operation_id: UUID | None = None):
        super().__init__("BROWSER_LEDGER_CONFLICT", RetryDisposition.OPERATOR, operation_id)
