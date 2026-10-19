# File: backend/app/presentation/task_dtos.py
"""Pydantic DTOs for Standalone ReportTask presentation API."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class StartTaskRequest(BaseModel):
    command_id: UUID
    expected_version: int = Field(ge=1)


class StopTaskRequest(BaseModel):
    command_id: UUID
    expected_version: int = Field(ge=1)
    attempt_id: Optional[UUID] = None


class RetryTaskRequest(BaseModel):
    expected_version: int = Field(ge=1)


class TaskViewDTO(BaseModel):
    id: UUID
    operator_id: UUID
    owner_profile_id: Optional[UUID]
    name: str
    original_url: Optional[str]
    explanation: Optional[str] = None
    preferred_country: Optional[str] = None
    status: str
    version: int
    retry_count: int
    max_retries: int
    target_urls: List[str]
    created_at: datetime
    updated_at: datetime
    submitted_at: Optional[datetime] = None
    attempt_id: Optional[UUID] = None
    completed_at: Optional[datetime] = None
    safe_error_code: Optional[str] = None
    receipt_text: Optional[str] = None
    case_number: Optional[str] = None
    is_active: bool
    is_terminal: bool
    is_retriable: bool
    is_running: bool
    is_legacy: bool = False
    legacy_read_only: bool = False


class TaskPageDTO(BaseModel):
    items: List[TaskViewDTO]
    limit: int
    offset: int
    has_more: bool


class StartReceiptDTO(BaseModel):
    task_id: UUID
    command_id: UUID
    attempt_id: UUID
    version: int
    status: str
    historical: bool = False
    authority_contract_version: int
    legacy_outcome_phase: Optional[str] = None
    safe_code: Optional[str] = None


class ControlViewDTO(BaseModel):
    command_id: UUID
    status: str
    safe_code: str


class ExecutionAvailabilityDTO(BaseModel):
    available: bool
    reason: str
