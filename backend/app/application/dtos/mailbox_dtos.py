# File: backend/app/application/dtos/mailbox_dtos.py
from dataclasses import asdict
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.domain.value_objects.mailbox_verification import MailboxConnectionView


class BeginMailboxLoginDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_hint: str | None = Field(None, max_length=254)


class MailboxConfigurationDTO(BaseModel):
    login_configured: bool
    client_id: str
    template_version: str
    template_label: str


class ConfigureMailboxClientDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_id: UUID


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


class DeviceLoginPromptDTO(BaseModel):
    login_id: str
    verification_uri: str
    user_code: str = Field(repr=False)
    expires_at: datetime
    interval_seconds: int
