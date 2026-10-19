# File: backend/app/domain/entities/operator_account.py
"""Operator account domain entity with state, versions, and validation."""

from datetime import datetime
import re
from typing import Optional
from uuid import UUID
from app.domain.value_objects.operator_identity import OperatorAccountStatus

USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,63}$")


class OperatorAccount:
    """Represents an operator user with separate authentication and run versions."""

    def __init__(
        self,
        id: UUID,
        username_key: Optional[str],
        username_display: Optional[str],
        password_hash: Optional[str],
        status: OperatorAccountStatus,
        auth_version: int,
        run_version: int,
        created_at: datetime,
        updated_at: datetime,
    ):
        self.id = id
        self.username_key = username_key
        self.username_display = username_display
        self._password_hash = password_hash
        self.status = status
        self.auth_version = max(1, auth_version)
        self.run_version = max(1, run_version)
        self.created_at = created_at
        self.updated_at = updated_at

    @property
    def password_hash(self) -> Optional[str]:
        return self._password_hash

    @property
    def is_active(self) -> bool:
        return self.status == OperatorAccountStatus.ACTIVE

    @property
    def is_disabled(self) -> bool:
        return self.status == OperatorAccountStatus.DISABLED

    @property
    def is_quarantined(self) -> bool:
        return self.status == OperatorAccountStatus.QUARANTINED

    @staticmethod
    def normalize_username(raw: str) -> tuple[str, str]:
        display = raw.strip()
        key = display.casefold()
        if not USERNAME_PATTERN.match(key):
            raise ValueError(
                "Username must match ^[a-z0-9][a-z0-9_.-]{2,63}$"
            )
        return key, display

    @staticmethod
    def validate_password_bounds(password: str) -> None:
        if len(password) < 12 or len(password) > 256:
            raise ValueError("Password must be between 12 and 256 characters")
        if len(password.encode("utf-8")) > 1024:
            raise ValueError("Password UTF-8 bytes must not exceed 1024 bytes")

    def bump_auth_version(self) -> None:
        self.auth_version += 1

    def bump_run_version(self) -> None:
        self.run_version += 1

    def set_password_hash(self, encoded_hash: str) -> None:
        self._password_hash = encoded_hash
        self.bump_auth_version()

    def disable(self) -> None:
        self.status = OperatorAccountStatus.DISABLED
        self.bump_auth_version()
        self.bump_run_version()

    def enable(self) -> None:
        self.status = OperatorAccountStatus.ACTIVE
        self.bump_auth_version()
        self.bump_run_version()

    def __repr__(self) -> str:
        return (
            f"OperatorAccount(id={self.id}, username={self.username_key}, "
            f"status={self.status.value}, auth_v={self.auth_version}, run_v={self.run_version})"
        )
