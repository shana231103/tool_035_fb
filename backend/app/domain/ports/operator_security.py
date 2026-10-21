# File: backend/app/domain/ports/operator_security.py
"""Domain port interfaces for security, clock, accounts, sessions, and limits."""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from app.domain.entities.operator_account import OperatorAccount
from app.domain.entities.proxy_item import ProxyItem
from app.domain.value_objects.operator_identity import (
    AccountMetadata,
    SessionRecord,
    SessionStatus,
    ValidatedProxyEndpoint,
)


class IPasswordHasher(ABC):
    @abstractmethod
    async def hash(self, password: str) -> str:
        raise NotImplementedError

    @abstractmethod
    async def verify(self, encoded: str, password: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def needs_rehash(self, encoded: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def shutdown(self) -> None:
        raise NotImplementedError


class IClock(ABC):
    @abstractmethod
    def now(self) -> datetime:
        raise NotImplementedError

    @abstractmethod
    def monotonic(self) -> float:
        raise NotImplementedError


class IAccountRepository(ABC):
    @abstractmethod
    async def find_login(self, username_key: str) -> Optional[OperatorAccount]:
        raise NotImplementedError

    @abstractmethod
    async def get(self, id: UUID) -> Optional[OperatorAccount]:
        raise NotImplementedError

    @abstractmethod
    async def lock(self, id: UUID) -> OperatorAccount:
        raise NotImplementedError

    @abstractmethod
    async def insert(self, account: OperatorAccount) -> None:
        raise NotImplementedError

    @abstractmethod
    async def change_credentials(
        self, id: UUID, expected_version: int, encoded_hash: str
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def set_enabled(self, id: UUID, enabled: bool) -> None:
        raise NotImplementedError

    @abstractmethod
    async def bump_auth_version(self, id: UUID) -> None:
        raise NotImplementedError

    @abstractmethod
    async def list_metadata(self, limit: int, offset: int) -> List[AccountMetadata]:
        raise NotImplementedError


class ISessionRepository(ABC):
    @abstractmethod
    async def get_by_id(self, id: UUID) -> Optional[SessionRecord]:
        raise NotImplementedError

    @abstractmethod
    async def get_by_digest(self, digest: bytes) -> Optional[SessionRecord]:
        raise NotImplementedError

    @abstractmethod
    async def insert(self, record: SessionRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    async def touch(
        self, id: UUID, expected_auth_version: int, now: datetime, *,
        min_interval: timedelta = timedelta(0),
    ) -> bool:
        """Advance a valid session only after its persisted activity interval."""
        raise NotImplementedError

    @abstractmethod
    async def revoke(self, id: UUID, now: datetime) -> None:
        raise NotImplementedError

    @abstractmethod
    async def revoke_account(self, id: UUID, now: datetime) -> None:
        raise NotImplementedError

    @abstractmethod
    async def list_valid(
        self, ids: Tuple[UUID, ...], now: datetime
    ) -> Dict[UUID, SessionStatus]:
        raise NotImplementedError

    @abstractmethod
    async def prune(self, before: datetime, limit: int) -> int:
        raise NotImplementedError


class ISessionSecrets(ABC):
    @abstractmethod
    def new_secret(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def digest(self, secret: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def csrf(self, secret: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def verify_csrf(self, secret: str, supplied: str) -> bool:
        raise NotImplementedError


class ILoginLimits(ABC):
    @abstractmethod
    async def acquire(self, username_key: str, client_ip: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def record_failure(self, username_key: str, client_ip: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def record_success(self, username_key: str, client_ip: str) -> None:
        raise NotImplementedError


class IProxyEndpointPolicy(ABC):
    @abstractmethod
    async def prepare(
        self, proxy: ProxyItem, deadline: float
    ) -> ValidatedProxyEndpoint:
        raise NotImplementedError
