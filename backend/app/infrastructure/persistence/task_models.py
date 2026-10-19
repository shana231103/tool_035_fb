# File: backend/app/infrastructure/persistence/task_models.py
"""SQLAlchemy models for standalone tasks, execution slots, receipts, and links."""

from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from app.infrastructure.persistence.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


DEFAULT_ACCOUNT_ID = "00000000-0000-0000-0000-000000000001"


class ReportTaskModel(Base):
    __tablename__ = "report_tasks"

    id = Column(String(36), primary_key=True)
    operator_account_id = Column(
        String(36),
        ForeignKey("operator_accounts.id"),
        nullable=False,
        default=DEFAULT_ACCOUNT_ID,
        index=True,
    )
    name = Column(String(255), nullable=False, default="Report Task")
    owner_profile_id = Column(String(36), nullable=True)
    preferred_country = Column(String(10), nullable=True)
    target_urls_json = Column(Text, nullable=False, default="[]")
    version = Column(Integer, nullable=False, default=1)
    run_version = Column(Integer, nullable=True)
    last_start_command_id = Column(String(36), nullable=True)
    legacy_read_only = Column(Boolean, nullable=False, default=False)
    display_summary = Column(Text, nullable=True)

    legacy_batch_job_id = Column(String(36), ForeignKey("batch_jobs.id"), nullable=True)
    batch_job_id = Column(String(36), ForeignKey("batch_jobs.id"), nullable=True)
    target_url = Column(Text, nullable=True)
    target_platform = Column(String(50), nullable=True, default="FACEBOOK")
    target_content_type = Column(String(50), nullable=True, default="post")
    original_url = Column(Text, nullable=False)
    explanation = Column(Text, nullable=False)
    status = Column(String(50), default="DRAFT")
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    proxy_id = Column(String(36), nullable=True)
    meta_case_number = Column(String(100), nullable=True)
    screenshot_path = Column(String(500), nullable=True)
    error_message = Column(Text, nullable=True)
    infringing_account = Column(String(255), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    attempt_id = Column(String(36), nullable=True)
    input_snapshot = Column(JSON, nullable=True)
    verification = Column(JSON, nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    receipt_text = Column(Text, nullable=True)

    batch_job = relationship("BatchJobModel", back_populates="tasks", foreign_keys=[batch_job_id])

    __table_args__ = (
        UniqueConstraint("id", "operator_account_id", name="uq_report_tasks_owner"),
        CheckConstraint("version >= 1", name="ck_report_task_version_positive"),
        ForeignKeyConstraint(
            ["owner_profile_id", "operator_account_id"],
            ["owner_profiles.id", "owner_profiles.operator_account_id"],
            name="fk_report_tasks_profile_owner",
        ),
        Index("ix_report_tasks_operator_created", "operator_account_id", "created_at", "id"),
        Index("ix_report_tasks_operator_status", "operator_account_id", "status", "updated_at"),
    )


class TaskExecutionSlotModel(Base):
    __tablename__ = "task_execution_slot"

    singleton_id = Column(Integer, primary_key=True, default=1)
    generation = Column(Integer, nullable=False, default=0)
    phase = Column(String(30), nullable=False, default="FREE")

    task_id = Column(String(36), nullable=True)
    operator_account_id = Column(String(36), nullable=True)
    attempt_id = Column(String(36), nullable=True)
    run_version = Column(Integer, nullable=True)
    command_id = Column(String(36), nullable=True)
    runtime_epoch = Column(String(36), nullable=True)
    admitted_at = Column(DateTime(timezone=True), nullable=True)

    recovery_id = Column(String(36), nullable=True)
    recovery_reason = Column(Text, nullable=True)
    recovery_started_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("singleton_id = 1", name="ck_task_execution_slot_singleton"),
        CheckConstraint("generation >= 0", name="ck_slot_generation_nonnegative"),
        ForeignKeyConstraint(["task_id", "operator_account_id"], ["report_tasks.id", "report_tasks.operator_account_id"], name="fk_slot_task_owner"),
        CheckConstraint(
            "(phase = 'FREE' AND task_id IS NULL AND operator_account_id IS NULL AND attempt_id IS NULL AND run_version IS NULL AND command_id IS NULL AND runtime_epoch IS NULL AND admitted_at IS NULL AND recovery_id IS NULL AND recovery_reason IS NULL AND recovery_started_at IS NULL) OR "
            "(phase IN ('ADMITTED', 'RUNNING', 'DRAINING') AND task_id IS NOT NULL AND operator_account_id IS NOT NULL AND attempt_id IS NOT NULL AND run_version IS NOT NULL AND command_id IS NOT NULL AND runtime_epoch IS NOT NULL AND admitted_at IS NOT NULL AND recovery_id IS NULL AND recovery_reason IS NULL AND recovery_started_at IS NULL) OR "
            "(phase = 'RECOVERY_REQUIRED' AND recovery_id IS NOT NULL AND recovery_reason IS NOT NULL AND recovery_started_at IS NOT NULL AND ("
            "(task_id IS NOT NULL AND operator_account_id IS NOT NULL AND attempt_id IS NOT NULL AND run_version IS NOT NULL AND command_id IS NOT NULL AND runtime_epoch IS NOT NULL AND admitted_at IS NOT NULL) OR "
            "(task_id IS NULL AND operator_account_id IS NULL AND attempt_id IS NULL AND run_version IS NULL AND command_id IS NULL AND runtime_epoch IS NULL AND admitted_at IS NULL)))",
            name="ck_task_execution_slot_phase_invariants",
        ),
    )


class TaskArtifactLinkModel(Base):
    __tablename__ = "task_artifact_links"

    artifact_id = Column(String(36), primary_key=True)
    task_id = Column(String(36), primary_key=True)
    operator_account_id = Column(
        String(36), ForeignKey("operator_accounts.id"), nullable=False, index=True
    )
    kind = Column(String(20), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        ForeignKeyConstraint(
            ["task_id", "operator_account_id"],
            ["report_tasks.id", "report_tasks.operator_account_id"],
            name="fk_task_artifact_links_task",
        ),
        ForeignKeyConstraint(["artifact_id", "operator_account_id", "kind"], ["operator_artifacts.id", "operator_artifacts.operator_account_id", "operator_artifacts.kind"], name="fk_task_artifact_links_artifact_owner_kind"),
        Index("ix_task_artifact_links_lookup", "task_id", "operator_account_id"),
    )

# Compatibility imports retain one ORM registration.
from app.infrastructure.persistence.task_receipt_models import TaskStartReceiptModel, TaskControlReceiptModel
