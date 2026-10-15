# File: backend/app/domain/value_objects/browser_status.py
from dataclasses import dataclass
from enum import Enum
from uuid import UUID
from app.domain.exceptions.browser_errors import safe_browser_reason
from app.domain.value_objects.browser_session import BrowserSessionRecord, bounded_ascii, require_uuid


class ReadinessState(str, Enum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    STARTING = "STARTING"
    CLOSED = "CLOSED"


class TaskCleanupState(str, Enum):
    CLEAR = "CLEAR"
    PENDING = "PENDING"
    UNRESOLVED = "UNRESOLVED"


class CleanupOutcomeState(str, Enum):
    CLOSED = "CLOSED"
    PENDING = "PENDING"
    UNRESOLVED = "UNRESOLVED"


class CleanupConfirmation(str, Enum):
    ACKNOWLEDGED = "ACKNOWLEDGED"
    NOT_CREATED = "NOT_CREATED"
    EXTERNAL = "EXTERNAL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class BrowserReadiness:
    state: ReadinessState = ReadinessState.STARTING
    can_start: bool = False
    charged_count: int = 0
    limit: int = 1
    pending_count: int = 0
    unknown_count: int = 0
    safe_reason: str | None = None
    startup_classified: bool = False

    def __post_init__(self):
        object.__setattr__(self, "state", ReadinessState(self.state))
        object.__setattr__(self, "safe_reason", safe_browser_reason(self.safe_reason))
        if min(self.charged_count, self.limit, self.pending_count, self.unknown_count) < 0:
            raise ValueError("Browser readiness counters cannot be negative.")
        if self.can_start and (self.state not in {ReadinessState.READY, ReadinessState.DEGRADED} or not self.startup_classified or self.charged_count >= self.limit):
            raise ValueError("Browser admission requires classified available capacity.")


@dataclass(frozen=True)
class BrowserTaskResourceStatus:
    task_id: UUID
    resource_allows_retry: bool
    cleanup_state: TaskCleanupState = TaskCleanupState.CLEAR
    operation_refs: tuple[UUID, ...] = ()
    safe_reason: str | None = None

    def __post_init__(self):
        require_uuid(self.task_id, *self.operation_refs)
        object.__setattr__(self, "cleanup_state", TaskCleanupState(self.cleanup_state))
        object.__setattr__(self, "safe_reason", safe_browser_reason(self.safe_reason))
        if self.resource_allows_retry and (self.cleanup_state != TaskCleanupState.CLEAR or self.operation_refs):
            raise ValueError("Unclosed resources prohibit retry.")


@dataclass(frozen=True)
class BrowserStatus:
    readiness: BrowserReadiness
    task: BrowserTaskResourceStatus | None = None


@dataclass(frozen=True)
class RuntimeBinding:
    installation_id: UUID
    provider_binding_id: UUID
    host_binding_digest: str
    schema_version: int = 1

    def __post_init__(self):
        require_uuid(self.installation_id, self.provider_binding_id)
        bounded_ascii(self.host_binding_digest, "host binding digest")
        if self.schema_version != 1:
            raise ValueError("Unsupported browser binding schema.")


@dataclass(frozen=True)
class BrowserBootstrapSnapshot:
    binding: RuntimeBinding | None
    unclosed_records: tuple[BrowserSessionRecord, ...]
    total_ledger_rows: int
    total_charged: int
    complete: bool


@dataclass(frozen=True)
class BrowserLedgerCounts:
    charged: int = 0
    pending: int = 0
    unknown: int = 0
    unclosed: int = 0

    def __post_init__(self):
        if min(self.charged, self.pending, self.unknown, self.unclosed) < 0:
            raise ValueError("Browser ledger counts cannot be negative.")


@dataclass(frozen=True)
class CleanupOutcome:
    operation_id: UUID
    state: CleanupOutcomeState
    reason: str | None = None
    confirmation: CleanupConfirmation = CleanupConfirmation.UNKNOWN

    def __post_init__(self):
        require_uuid(self.operation_id)
        object.__setattr__(self, "state", CleanupOutcomeState(self.state))
        object.__setattr__(self, "confirmation", CleanupConfirmation(self.confirmation))
        object.__setattr__(self, "reason", safe_browser_reason(self.reason))
        if self.state == CleanupOutcomeState.CLOSED and self.confirmation == CleanupConfirmation.UNKNOWN:
            raise ValueError("Closed cleanup requires confirmation.")


@dataclass(frozen=True)
class ExternalCleanupConfirmation:
    operation_id: UUID
    expected_version: int
    audit_reference: str
    provider_mutation_terminal: bool
    confirmed_by_local_operator: bool
    evidence_kind: str = "VERIFIED_EXTERNAL_AUDIT"

    def __post_init__(self):
        require_uuid(self.operation_id)
        bounded_ascii(self.audit_reference, "audit reference")
        if self.expected_version < 0 or self.evidence_kind != "VERIFIED_EXTERNAL_AUDIT":
            raise ValueError("Invalid external cleanup attestation.")
