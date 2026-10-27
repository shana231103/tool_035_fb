# File: backend/app/presentation/bulk_job_dtos.py
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.application.bulk_import_models import (
    BulkMailboxRef, BulkPreviewCommand, CreateBulkBatchCommand,
)
from app.domain.value_objects.enums import ProxyCountry


class BulkMailboxRefDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_line: int = Field(ge=1)
    expected_email: str = Field(min_length=3, max_length=254)
    connection_id: UUID


class BulkPreviewRequestDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    profile_id: UUID
    orders_text: str
    mailboxes: list[BulkMailboxRefDTO] = Field(min_length=1, max_length=100)
    preferred_country: ProxyCountry | None = None
    custom_explanation: str | None = Field(default=None, max_length=500)

    def to_command(self):
        return BulkPreviewCommand(self.name, self.profile_id, self.orders_text,
            tuple(BulkMailboxRef(row.source_line, row.expected_email, row.connection_id)
                  for row in self.mailboxes), self.preferred_country, self.custom_explanation)


class BulkCreateRequestDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    import_id: UUID
    preview: BulkPreviewRequestDTO
    expected_profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    preview_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    duplicate_ack_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    def to_command(self):
        return CreateBulkBatchCommand(self.import_id, self.preview.to_command(),
            self.expected_profile_sha256, self.preview_sha256, self.duplicate_ack_sha256)


class BulkStartRequestDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bulk_review_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
