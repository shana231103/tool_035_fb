# File: backend/app/application/dtos/profile_dtos.py
from datetime import datetime
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, Field
from app.domain.value_objects.enums import OwnerRole


class CreateProfileRequestDTO(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255)
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    country: str = Field(..., min_length=2, max_length=10)
    organization_name: str = Field("", max_length=255)
    rights_owner_name: str = Field(..., min_length=2, max_length=255)
    sender_name: str = Field(..., min_length=2, max_length=255)
    rights_jurisdiction: str = Field(..., min_length=2, max_length=255)
    owner_role: Literal[OwnerRole.OWNER]


class ProfileResponseDTO(BaseModel):
    id: UUID
    full_name: str
    email: str
    country: str
    organization_name: str
    created_at: datetime
    rights_owner_name: str | None = None
    sender_name: str | None = None
    rights_jurisdiction: str | None = None
    owner_role: OwnerRole | None = None
    needs_completion: bool = True
    submission_eligible: bool = False
    submission_block_reason: str | None = None
