# File: backend/app/application/operator_records.py
"""Application data transfer records and commands for operator auth and maintenance."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID
from app.domain.value_objects.operator_identity import (
    AccountMetadata,
    OperatorAccountStatus,
)


@dataclass(frozen=True)
class LoginCommand:
    username: str
    password: str


@dataclass(frozen=True)
class SessionView:
    authenticated: bool
    operator: Optional[Dict[str, str]] = None
    session_context: Optional[UUID] = None
    csrf_token: Optional[str] = None
    expires_at: Optional[datetime] = None
    idle_expires_at: Optional[datetime] = None

    @classmethod
    def anonymous(cls) -> "SessionView":
        return cls(authenticated=False)


@dataclass(frozen=True)
class SessionGrant:
    view: SessionView
    cookie_secret: str


@dataclass(frozen=True)
class AssignmentManifest:
    manifest_id: UUID
    target_account_id: UUID
    schema_version: str
    components_count: int
    records_count: Dict[str, int]
    source_digest: str
    created_at: datetime


@dataclass(frozen=True)
class AssignmentReport:
    manifest_id: UUID
    applied_at: datetime
    records_updated: Dict[str, int]
    status: str
