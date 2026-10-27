# File: backend/app/infrastructure/persistence/models.py
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    CheckConstraint, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship
from app.infrastructure.persistence.database import Base
from app.infrastructure.persistence.browser_session_model import BrowserRuntimeBindingModel, BrowserSessionModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


class OwnerProfileModel(Base):
    __tablename__ = "owner_profiles"

    id = Column(String(36), primary_key=True)
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    country = Column(String(10), nullable=False)
    organization_name = Column(String(255), default="")
    created_at = Column(DateTime(timezone=True), default=_now)

    rights_owner_name = Column(String(255), nullable=True)
    sender_name = Column(String(255), nullable=True)
    rights_jurisdiction = Column(String(255), nullable=True)
    owner_role = Column(String(255), nullable=True)

    jobs = relationship("BatchJobModel", back_populates="owner_profile")


class ProxyModel(Base):
    __tablename__ = "proxies"

    id = Column(String(36), primary_key=True)
    protocol = Column(String(10), default="http")
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False)
    country = Column(String(10), nullable=False)
    username = Column(String(255), nullable=True)
    password = Column(String(255), nullable=True)
    status = Column(String(20), default="TESTING")
    latency_ms = Column(Integer, default=-1)
    consecutive_failures = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=_now)
    last_checked_at = Column(DateTime(timezone=True), nullable=True)


class BatchJobModel(Base):
    __tablename__ = "batch_jobs"
    __table_args__ = (
        CheckConstraint("(bulk_import_id IS NULL AND bulk_import_version IS NULL AND bulk_request_sha256 IS NULL AND bulk_content_sha256 IS NULL AND bulk_profile_sha256 IS NULL AND bulk_mail_pool IS NULL AND bulk_revision IS NULL AND bulk_last_acceptance IS NULL AND bulk_pause_reason IS NULL) OR (bulk_import_id IS NOT NULL AND bulk_import_version IS NOT NULL AND bulk_import_version = 1 AND bulk_request_sha256 IS NOT NULL AND length(bulk_request_sha256) = 64 AND bulk_content_sha256 IS NOT NULL AND length(bulk_content_sha256) = 64 AND bulk_profile_sha256 IS NOT NULL AND length(bulk_profile_sha256) = 64 AND bulk_mail_pool IS NOT NULL AND bulk_revision IS NOT NULL AND bulk_revision >= 1)", name="ck_bulk_job_metadata"),
    )

    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    owner_profile_id = Column(String(36), ForeignKey("owner_profiles.id"), nullable=False)
    preferred_country = Column(String(10), nullable=True)
    concurrency = Column(Integer, default=2)
    delay_min = Column(Integer, default=30)
    delay_max = Column(Integer, default=90)
    status = Column(String(20), default="PENDING")
    created_at = Column(DateTime(timezone=True), default=_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    bulk_import_id = Column(String(36), nullable=True, unique=True)
    bulk_import_version = Column(Integer, nullable=True)
    bulk_request_sha256 = Column(String(64), nullable=True)
    bulk_content_sha256 = Column(String(64), nullable=True, index=True)
    bulk_profile_sha256 = Column(String(64), nullable=True)
    bulk_mail_pool = Column(JSON(none_as_null=True), nullable=True)
    bulk_revision = Column(Integer, nullable=True)
    bulk_last_acceptance = Column(JSON(none_as_null=True), nullable=True)
    bulk_pause_reason = Column(String(64), nullable=True)

    owner_profile = relationship("OwnerProfileModel", back_populates="jobs")
    tasks = relationship("ReportTaskModel", back_populates="batch_job", cascade="all, delete-orphan")


class ReportTaskModel(Base):
    __tablename__ = "report_tasks"
    __table_args__ = (
        UniqueConstraint("batch_job_id", "bulk_sequence", name="uq_bulk_task_sequence"),
        CheckConstraint("(bulk_sequence IS NULL AND bulk_source_line IS NULL AND assigned_mail_email IS NULL) OR (bulk_sequence IS NOT NULL AND bulk_source_line IS NOT NULL AND bulk_sequence >= 1 AND bulk_sequence <= 1000 AND bulk_source_line >= 1 AND assigned_mail_email IS NOT NULL)", name="ck_bulk_task_assignment"),
        CheckConstraint("dispatch_revision >= 0", name="ck_task_dispatch_revision"),
        Index("ix_task_dispatch_candidates", "batch_job_id", "status", "bulk_sequence", "id"),
    )

    id = Column(String(36), primary_key=True)
    batch_job_id = Column(String(36), ForeignKey("batch_jobs.id"), nullable=False)
    target_url = Column(Text, nullable=False)
    target_platform = Column(String(50), nullable=False)
    target_content_type = Column(String(50), nullable=False)
    original_url = Column(Text, nullable=False)
    explanation = Column(Text, nullable=False)
    status = Column(String(20), default="PENDING")
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    proxy_id = Column(String(36), nullable=True)
    meta_case_number = Column(String(100), nullable=True)
    screenshot_path = Column(String(500), nullable=True)
    error_message = Column(Text, nullable=True)
    infringing_account = Column(String(255), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    attempt_id = Column(String(36), nullable=True)
    input_snapshot = Column(JSON, nullable=True)
    verification = Column(JSON, nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    receipt_text = Column(Text, nullable=True)
    bulk_sequence = Column(Integer, nullable=True)
    bulk_source_line = Column(Integer, nullable=True)
    assigned_mail_email = Column(String(255), nullable=True)
    dispatch_revision = Column(Integer, nullable=False, default=0, server_default="0")
    waiting_reason = Column(String(64), nullable=True)

    batch_job = relationship("BatchJobModel", back_populates="tasks")
