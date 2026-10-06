# File: backend/app/domain/exceptions/mailbox_errors.py
SAFE_MAILBOX_REASONS = frozenset({
    "AUTH_REQUIRED", "CONSENT_REQUIRED", "MAILBOX_UNAVAILABLE", "MAPPING_INVALID",
    "BUSY", "DISCONNECTED", "GRAPH_LINK_REJECTED", "GRAPH_PROTOCOL_ERROR",
    "READ_BUDGET_EXHAUSTED", "CORRELATION_UNRESOLVED", "CORRELATION_AMBIGUOUS",
    "EVIDENCE_REQUIRED", "CODE_REPLAY", "STALE", "LOGIN_EXPIRED", "LOGIN_CANCELLED",
    "VERIFICATION_FAILED", "VERIFICATION_TIMEOUT", "THROTTLED", "CONFIGURATION_REQUIRED", "MAIL_READ_REQUIRED",
    "GRAPH_ACCESS_DENIED", "GRAPH_AUTH_REJECTED", "MAILBOX_NOT_SUPPORTED",
    "APP_CONSENT_REQUIRED",
})


class MailboxError(ValueError):
    """Allowlisted reason only; provider payloads must never be attached."""

    def __init__(self, reason: str):
        self.reason = reason if reason in SAFE_MAILBOX_REASONS else "MAILBOX_UNAVAILABLE"
        super().__init__(self.reason)
