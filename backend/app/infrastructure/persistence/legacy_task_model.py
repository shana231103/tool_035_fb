# File: backend/app/infrastructure/persistence/legacy_task_model.py
"""SQLAlchemy model for archived legacy task metadata."""

from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, String, Text
from app.infrastructure.persistence.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class LegacyTaskMetadataModel(Base):
    """Append-only storage for pre-005/pre-006 legacy task metadata and provenance."""
    __tablename__ = "legacy_task_metadata"

    id = Column(String(36), primary_key=True)
    source_revision = Column(String(50), nullable=False)
    raw_task_id = Column(String(36), nullable=True, index=True)
    raw_batch_job_id = Column(String(36), nullable=True)
    raw_profile_id = Column(String(36), nullable=True)
    raw_proxy_id = Column(String(36), nullable=True)
    raw_status = Column(String(50), nullable=True)
    raw_targets = Column(Text, nullable=True)
    raw_evidence = Column(Text, nullable=True)
    pre_conversion_digest = Column(String(64), nullable=True)
    disposition = Column(String(50), nullable=False, default="READONLY")
    provenance = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
