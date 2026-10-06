# File: backend/app/application/dtos/job_dtos.py
from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator
from app.application.dtos.verification_dtos import safe_verification_metadata
from app.domain.value_objects.enums import JobStatus, ProxyCountry, TaskStatus


class CreateBatchJobRequestDTO(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    owner_profile_id: UUID
    target_urls: List[str] = Field(..., min_length=1)
    original_work_url: str = Field(..., min_length=1)
    preferred_country: Optional[ProxyCountry] = None
    concurrency: int = Field(1, ge=1, le=10)
    delay_min: int = Field(0, ge=0)
    delay_max: int = Field(0, ge=0)
    custom_explanation: Optional[str] = Field(None, max_length=500)

    @field_validator("original_work_url")
    @classmethod
    def nonblank_original(cls, value):
        if not value.strip():
            raise ValueError("A public original work URL is required.")
        return value.strip()

    @field_validator("custom_explanation")
    @classmethod
    def validate_custom_explanation(cls, value):
        if value is None:
            return None
        cleaned = value.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not cleaned:
            return None
        if len(cleaned) > 500:
            raise ValueError("Custom explanation must not exceed 500 characters.")
        return cleaned


class ReportTaskResponseDTO(BaseModel):
    @field_validator("verification", mode="before")
    @classmethod
    def safe_metadata(cls, value):
        return safe_verification_metadata(value if isinstance(value, dict) else {})

    id: UUID
    batch_job_id: UUID
    target_url: str
    target_platform: str
    target_content_type: str
    original_url: str
    status: TaskStatus
    retry_count: int
    max_retries: int = Field(3, ge=0)
    proxy_id: Optional[UUID] = None
    meta_case_number: Optional[str] = None
    screenshot_path: Optional[str] = None
    error_message: Optional[str] = None
    infringing_account: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    attempt_id: Optional[str] = None
    verification: dict = Field(default_factory=dict)
    submitted_at: Optional[datetime] = None
    receipt_text: Optional[str] = None


class BatchJobResponseDTO(BaseModel):
    id: UUID
    name: str
    owner_profile_id: UUID
    preferred_country: Optional[ProxyCountry] = None
    concurrency: int
    delay_min: int
    delay_max: int
    status: JobStatus
    created_at: datetime
    completed_at: Optional[datetime] = None
    stats: Dict[str, int]
    tasks: List[ReportTaskResponseDTO] = []


class BatchJobPageResponseDTO(BaseModel):
    items: List[BatchJobResponseDTO]
    limit: int = Field(..., ge=1, le=100)
    offset: int = Field(..., ge=0)
    has_more: bool
