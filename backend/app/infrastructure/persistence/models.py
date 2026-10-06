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
)
from sqlalchemy.orm import relationship
from app.infrastructure.persistence.database import Base


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

    owner_profile = relationship("OwnerProfileModel", back_populates="jobs")
    tasks = relationship("ReportTaskModel", back_populates="batch_job", cascade="all, delete-orphan")


class ReportTaskModel(Base):
    __tablename__ = "report_tasks"

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

    batch_job = relationship("BatchJobModel", back_populates="tasks")
