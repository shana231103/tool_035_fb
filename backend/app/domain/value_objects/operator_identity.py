# File: backend/app/domain/value_objects/operator_identity.py
"""Immutable domain value objects for operator identity, scope, and artifacts."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID


class OperatorAccountStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    QUARANTINED = "QUARANTINED"


class SessionStatus(str, Enum):
    VALID = "VALID"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    UNKNOWN = "UNKNOWN"


class ArtifactKind(str, Enum):
    PROOF = "PROOF"
    SCREENSHOT = "SCREENSHOT"


class ControlTargetKind(str, Enum):
    STOP_JOB = "STOP_JOB"
    STOP_TASK = "STOP_TASK"
    DISCONNECT_MAILBOX = "DISCONNECT_MAILBOX"


@dataclass(frozen=True)
class AccountMetadata:
    id: UUID
    username_display: str
    status: OperatorAccountStatus
    auth_version: int
    run_version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class OperatorPrincipal:
    operator_id: UUID
    session_id: UUID
    auth_version: int
    absolute_expires_at: datetime
    idle_expires_at: datetime


@dataclass(frozen=True)
class ExecutionScope:
    operator_id: UUID
    job_id: UUID
    run_version: int


@dataclass(frozen=True)
class ControlTarget:
    kind: ControlTargetKind
    operator_id: UUID
    resource_id: str
    generation: int


@dataclass(frozen=True)
class ControlAdmission:
    admission_id: UUID
    target: ControlTarget
    initiating_session_id: UUID
    observed_auth_version: int
    admitted_at: datetime


@dataclass(frozen=True)
class SessionRecord:
    id: UUID
    secret_digest: bytes
    operator_id: UUID
    auth_version: int
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    idle_expires_at: datetime
    revoked_at: Optional[datetime] = None


@dataclass(frozen=True)
class ArtifactRecord:
    id: UUID
    operator_id: UUID
    job_id: Optional[UUID]
    task_id: Optional[UUID]
    kind: ArtifactKind
    storage_key: str
    created_at: datetime


@dataclass(frozen=True)
class ProxyOwnerReference:
    proxy_id: UUID
    operator_id: UUID


@dataclass(frozen=True)
class ValidatedProxyEndpoint:
    protocol: str
    source_host: str
    connect_ip: str
    port: int
    tls_server_name: Optional[str]
    resolved_at: datetime
    valid_until: datetime
    credential_ref: Optional[str] = None
