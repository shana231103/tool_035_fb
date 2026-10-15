# File: backend/app/infrastructure/persistence/browser_session_model.py
from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from app.infrastructure.persistence.database import Base


class BrowserRuntimeBindingModel(Base):
    __tablename__ = "browser_runtime_bindings"
    singleton_id = Column(Integer, primary_key=True, default=1)
    installation_id = Column(String(36), nullable=False)
    provider_binding_id = Column(String(36), nullable=False)
    host_binding_digest = Column(String(128), nullable=False)
    schema_version = Column(Integer, nullable=False)
    __table_args__ = (CheckConstraint("singleton_id = 1", name="ck_browser_singleton"),)


class BrowserSessionModel(Base):
    __tablename__ = "browser_session_leases"
    operation_id = Column(String(36), primary_key=True)
    installation_id = Column(String(36), nullable=False)
    provider_binding_id = Column(String(36), nullable=False)
    task_id = Column(String(36), ForeignKey("report_tasks.id", ondelete="RESTRICT"), nullable=False)
    attempt_id = Column(String(36), nullable=False)
    marker_nonce = Column(String(128), nullable=False)
    profile_id = Column(String(128), nullable=True)
    phase = Column(String(32), nullable=False)
    cleanup_state = Column(String(32), nullable=False)
    version = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    retries = Column(Integer, nullable=False)
    safe_reason = Column(String(64), nullable=True)
    charged = Column(Boolean, nullable=False)
    completion_evidence = Column(String(32), nullable=False)
    audit_reference = Column(String(128), nullable=True)
    __table_args__ = (
        UniqueConstraint("installation_id", "task_id", "attempt_id", name="uq_browser_attempt"),
        UniqueConstraint("provider_binding_id", "profile_id", name="uq_browser_profile"),
        CheckConstraint("version >= 0 AND retries >= 0", name="ck_browser_counters"),
        CheckConstraint("(phase = 'CLOSED' AND charged = false AND cleanup_state = 'CONFIRMED' AND completion_evidence <> 'UNKNOWN') OR (phase <> 'CLOSED' AND charged = true)", name="ck_browser_charge"),
        Index("ix_browser_installation_charge", "installation_id", "charged", "updated_at"),
        Index("ix_browser_task_charge", "installation_id", "task_id", "charged"),
    )
