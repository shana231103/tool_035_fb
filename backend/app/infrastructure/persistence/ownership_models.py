# File: backend/app/infrastructure/persistence/ownership_models.py
"""SQLAlchemy models for proxy ownership references and operator artifacts."""

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    CheckConstraint,
    ForeignKeyConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from app.infrastructure.persistence.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ProxyOwnerRefModel(Base):
    __tablename__ = "proxy_owner_refs"

    proxy_id = Column(String(36), primary_key=True)
    operator_account_id = Column(
        String(36),
        ForeignKey("operator_accounts.id"),
        primary_key=True,
        index=True,
    )


class OperatorArtifactModel(Base):
    __tablename__ = "operator_artifacts"

    id = Column(String(36), primary_key=True)
    operator_account_id = Column(
        String(36),
        ForeignKey("operator_accounts.id"),
        nullable=False,
        index=True,
    )
    job_id = Column(String(36), nullable=True, index=True)
    task_id = Column(String(36), nullable=True, index=True)
    kind = Column(String(20), nullable=False)
    storage_key = Column(String(255), nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        CheckConstraint("job_id IS NOT NULL OR task_id IS NOT NULL", name="ck_artifact_resource"),
        UniqueConstraint("id", "operator_account_id", "kind", name="uq_artifact_owner_kind"),
        ForeignKeyConstraint(["task_id", "operator_account_id"], ["report_tasks.id", "report_tasks.operator_account_id"], name="fk_artifact_task_owner"),
        Index("ix_operator_artifacts_scope", "operator_account_id", "job_id"),
    )
