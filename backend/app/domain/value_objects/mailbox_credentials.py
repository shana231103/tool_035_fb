# File: backend/app/domain/value_objects/mailbox_credentials.py
from dataclasses import dataclass
from datetime import datetime
import unicodedata
from uuid import UUID

from app.domain.exceptions.mailbox_errors import MailboxError
from app.domain.value_objects.mailbox_verification import normalize_email

MAX_CREDENTIAL_BYTES = 16 * 1024


def _email(value: str) -> str:
    if not isinstance(value, str) or len(value.strip()) > 254:
        raise MailboxError("INVALID_CREDENTIAL_FORMAT")
    try:
        return normalize_email(value)
    except MailboxError:
        raise MailboxError("INVALID_CREDENTIAL_FORMAT") from None


@dataclass(frozen=True, repr=False)
class MailboxCredentials:
    email: str
    refresh_token: str
    client_id: str

    def __post_init__(self):
        object.__setattr__(self, "email", _email(self.email))
        if (not isinstance(self.refresh_token, str) or not self.refresh_token or
                any(c.isspace() or unicodedata.category(c).startswith("C") or c == "|"
                    for c in self.refresh_token)):
            raise MailboxError("INVALID_CREDENTIAL_FORMAT")
        try:
            client_id = str(UUID(self.client_id))
            size = len(f"{self.email}|{self.refresh_token}|{client_id}".encode("utf-8"))
        except (ValueError, TypeError, AttributeError, UnicodeError):
            raise MailboxError("INVALID_CREDENTIAL_FORMAT") from None
        if size > MAX_CREDENTIAL_BYTES:
            raise MailboxError("INVALID_CREDENTIAL_FORMAT")
        object.__setattr__(self, "client_id", client_id)


def parse_mailbox_credentials(raw: str) -> MailboxCredentials:
    try:
        valid = (isinstance(raw, str) and len(raw.encode("utf-8")) <= MAX_CREDENTIAL_BYTES
                 and not any(unicodedata.category(c).startswith("C") for c in raw))
    except UnicodeError:
        valid = False
    if not valid or raw.count("|") != 2:
        raise MailboxError("INVALID_CREDENTIAL_FORMAT")
    parts = tuple(part.strip() for part in raw.split("|"))
    if not all(parts):
        raise MailboxError("INVALID_CREDENTIAL_FORMAT")
    return MailboxCredentials(*parts)


@dataclass(frozen=True)
class MailboxAuthIdentity:
    provider_user_id: str
    primary_email: str

    def __post_init__(self):
        if (not isinstance(self.provider_user_id, str) or not self.provider_user_id.strip()
                or len(self.provider_user_id) > 1024
                or any(unicodedata.category(c).startswith("C") for c in self.provider_user_id)):
            raise MailboxError("GRAPH_PROTOCOL_ERROR")
        try:
            object.__setattr__(self, "primary_email", _email(self.primary_email))
        except MailboxError:
            raise MailboxError("GRAPH_PROTOCOL_ERROR") from None


@dataclass(frozen=True)
class MailboxConnectReservation:
    id: str
    expires_at: datetime


AuthIdentity = MailboxAuthIdentity
ConnectReservation = MailboxConnectReservation
