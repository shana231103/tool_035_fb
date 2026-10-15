# File: backend/app/domain/value_objects/browser_session.py
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID
from app.domain.exceptions.browser_errors import safe_browser_reason


class BrowserPhase(str, Enum):
    RESERVED = "RESERVED"
    CREATE_IN_FLIGHT = "CREATE_IN_FLIGHT"
    PROFILE_CREATED = "PROFILE_CREATED"
    START_IN_FLIGHT = "START_IN_FLIGHT"
    ATTACHED = "ATTACHED"
    RELEASING = "RELEASING"
    STOP_CONFIRMED = "STOP_CONFIRMED"
    DELETE_IN_FLIGHT = "DELETE_IN_FLIGHT"
    UNKNOWN_CREATE = "UNKNOWN_CREATE"
    CLEANUP_PENDING = "CLEANUP_PENDING"
    DELETE_UNKNOWN = "DELETE_UNKNOWN"
    NEEDS_OPERATOR = "NEEDS_OPERATOR"
    CLOSED = "CLOSED"


class CleanupState(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    RUNNING = "RUNNING"
    PENDING = "PENDING"
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"
    CONFIRMED = "CONFIRMED"
    UNRESOLVED = "UNRESOLVED"


class CompletionEvidence(str, Enum):
    UNKNOWN = "UNKNOWN"
    NOT_CREATED = "NOT_CREATED"
    DELETE_ACK = "DELETE_ACK"
    EXTERNAL = "EXTERNAL"


def bounded_ascii(value: str, label: str, limit: int = 128) -> None:
    if not isinstance(value, str) or not value or len(value) > limit or not value.isascii() or any(ord(c) < 33 or ord(c) > 126 for c in value):
        raise ValueError(f"Invalid {label}.")


def require_uuid(*values: UUID) -> None:
    if any(not isinstance(value, UUID) for value in values):
        raise ValueError("Browser identifiers must be UUIDs.")


def require_utc(value: datetime | None) -> None:
    if value is not None and (value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value)):
        raise ValueError("Browser timestamps must be aware UTC.")


@dataclass(frozen=True)
class ProxySpec:
    scheme: str
    host: str = field(repr=False)
    port: int
    username: str | None = field(default=None, repr=False)
    password: str | None = field(default=None, repr=False)

    def __post_init__(self):
        if self.scheme not in {"http", "https", "socks5"} or not 1 <= self.port <= 65535:
            raise ValueError("Invalid browser proxy.")
        if not self.host or any(c.isspace() or c in "/@?#" for c in self.host):
            raise ValueError("Invalid browser proxy host.")


@dataclass(frozen=True)
class BrowserSessionRequest:
    task_id: UUID
    attempt_id: UUID
    proxy: ProxySpec | None = field(default=None, repr=False)

    def __post_init__(self):
        require_uuid(self.task_id, self.attempt_id)


@dataclass(frozen=True)
class BrowserSessionRecord:
    operation_id: UUID
    installation_id: UUID
    provider_binding_id: UUID
    task_id: UUID
    attempt_id: UUID
    marker_nonce: str
    profile_id: str | None = field(default=None, repr=False)
    phase: BrowserPhase = BrowserPhase.RESERVED
    cleanup_state: CleanupState = CleanupState.NOT_STARTED
    version: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    next_retry_at: datetime | None = None
    retries: int = 0
    safe_reason: str | None = None
    charged: bool = True
    completion_evidence: CompletionEvidence = CompletionEvidence.UNKNOWN
    audit_reference: str | None = None

    def __post_init__(self):
        require_uuid(self.operation_id, self.installation_id, self.provider_binding_id, self.task_id, self.attempt_id)
        bounded_ascii(self.marker_nonce, "marker nonce")
        if self.profile_id is not None:
            bounded_ascii(self.profile_id, "profile identifier")
        for timestamp in (self.created_at, self.updated_at, self.next_retry_at):
            require_utc(timestamp)
        if self.version < 0 or self.retries < 0:
            raise ValueError("Browser counters cannot be negative.")
        object.__setattr__(self, "phase", BrowserPhase(self.phase))
        object.__setattr__(self, "cleanup_state", CleanupState(self.cleanup_state))
        object.__setattr__(self, "completion_evidence", CompletionEvidence(self.completion_evidence))
        object.__setattr__(self, "safe_reason", safe_browser_reason(self.safe_reason))
        if self.audit_reference is not None:
            bounded_ascii(self.audit_reference, "audit reference")
        closed = self.phase == BrowserPhase.CLOSED
        if closed != (not self.charged) or (closed and (self.cleanup_state != CleanupState.CONFIRMED or self.completion_evidence == CompletionEvidence.UNKNOWN)):
            raise ValueError("Only confirmed closed records may release their charge.")
        if closed and ((self.completion_evidence == CompletionEvidence.NOT_CREATED and self.profile_id is not None)
                       or (self.completion_evidence == CompletionEvidence.DELETE_ACK and self.profile_id is None)
                       or (self.completion_evidence == CompletionEvidence.EXTERNAL and self.audit_reference is None)):
            raise ValueError("Browser completion evidence requires consistent ownership proof.")


@dataclass(frozen=True)
class BrowserSessionMutation:
    next_phase: BrowserPhase
    next_cleanup_state: CleanupState
    newly_observed_profile_id: str | None = field(default=None, repr=False)
    safe_reason: str | None = None
    retry_count: int | None = None
    next_retry_at: datetime | None = None
    completion_evidence: CompletionEvidence = CompletionEvidence.UNKNOWN
    audit_reference: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "next_phase", BrowserPhase(self.next_phase))
        object.__setattr__(self, "next_cleanup_state", CleanupState(self.next_cleanup_state))
        object.__setattr__(self, "completion_evidence", CompletionEvidence(self.completion_evidence))
        object.__setattr__(self, "safe_reason", safe_browser_reason(self.safe_reason))
        if self.newly_observed_profile_id is not None:
            bounded_ascii(self.newly_observed_profile_id, "profile identifier")
        if self.audit_reference is not None:
            bounded_ascii(self.audit_reference, "audit reference")
        if self.retry_count is not None and self.retry_count < 0:
            raise ValueError("Browser retry counter cannot be negative.")
        require_utc(self.next_retry_at)
