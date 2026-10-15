# File: backend/app/domain/ports/mailbox_auth.py
from abc import ABC, abstractmethod

from app.domain.value_objects.mailbox_credentials import MailboxAuthIdentity, MailboxCredentials


class IMailboxAuth(ABC):
    @abstractmethod
    async def import_credentials(self, connection_id: str, credentials: MailboxCredentials,
                                 deadline: float) -> None:
        """Import a fresh reservation's credentials and obtain a delegated token."""

    @abstractmethod
    async def acquire_access_token(self, connection_id: str, deadline: float, *,
                                   force_refresh: bool = False) -> str:
        """Return a valid token, sharing one owned refresh per connection."""

    @abstractmethod
    def bind_identity(self, connection_id: str, identity: MailboxAuthIdentity) -> None:
        """Bind identity proved by Graph after mailbox access succeeds."""

    @abstractmethod
    def identity(self, connection_id: str) -> MailboxAuthIdentity:
        """Read already verified local identity without network IO."""

    @abstractmethod
    def assert_active(self, connection_id: str) -> None:
        """Reject a revoked or disposed connection without network IO."""

    @abstractmethod
    def revoke(self, connection_id: str) -> None:
        """Synchronously invalidate auth before lifecycle owners await cleanup."""

    @abstractmethod
    async def dispose(self, connection_id: str) -> None:
        """Invalidate first, then cancel/join owned work and release secrets."""

    @abstractmethod
    async def shutdown(self) -> None:
        """Drain all owned authentication work and close resources."""
