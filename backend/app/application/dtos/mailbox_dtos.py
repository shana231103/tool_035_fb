# File: backend/app/application/dtos/mailbox_dtos.py
from dataclasses import asdict
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from app.domain.value_objects.mailbox_verification import MailboxConnectionView


class ReserveMailboxDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MailboxCapabilitiesDTO(BaseModel):
    credential_format: str
    template_version: str
    template_label: str


class ConnectMailboxDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connection_id: UUID
    credentials: SecretStr = Field(repr=False)

    @field_validator("credentials")
    @classmethod
    def bounded_credentials(cls, value):
        try:
            valid = 0 < len(value.get_secret_value().encode("utf-8")) <= 16384
        except UnicodeError:
            valid = False
        if not valid:
            raise ValueError("Invalid credentials.")
        return value


class MailboxReservationDTO(BaseModel):
    id: str
    expires_at: datetime


class MailboxMappingDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meta_email: str = Field(min_length=3, max_length=254)
    primary_email: str = Field(default="", max_length=254)
    confirmed_aliases: tuple[str, ...] = Field(default=(), max_length=10)
    folders: tuple[Literal["inbox", "junkemail"], ...] = ("inbox",)
    template_version: str = Field(min_length=1, max_length=100)


class MailboxConnectionDTO(BaseModel):
    id: str
    status: Literal["pending", "connected", "reauth_required", "error", "disconnecting"]
    masked_email: str = ""
    mapped_email_masked: str | None = None
    expires_at: datetime | None = None
    safe_reason: str | None = None

    @classmethod
    def from_view(cls, view: MailboxConnectionView):
        return cls(**asdict(view))
