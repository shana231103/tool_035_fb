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
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import relationship
from app.infrastructure.persistence.database import Base
from app.infrastructure.persistence.browser_session_model import (
    BrowserRuntimeBindingModel,
    BrowserSessionModel,
)
from app.infrastructure.persistence.operator_models import (
    OperatorAccountModel,
    OperatorSessionModel,
)
from app.infrastructure.persistence.ownership_models import (
    OperatorArtifactModel,
    ProxyOwnerRefModel,
)
from app.infrastructure.persistence.legacy_task_model import LegacyTaskMetadataModel


DEFAULT_ACCOUNT_ID = "00000000-0000-0000-0000-000000000001"


def _now() -> datetime:
    return datetime.now(timezone.utc)


@event.listens_for(OperatorAccountModel.__table__, "after_create")
def _insert_default_account(target, connection, **kw):
    connection.execute(
        target.insert().values(
            id=DEFAULT_ACCOUNT_ID,
            username_key="system_default",
            username_display="system_default",
            password_hash="dummy_hash",
            status="QUARANTINED",
            auth_version=1,
            run_version=1,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )


class OwnerProfileModel(Base):
    __tablename__ = "owner_profiles"

    id = Column(String(36), primary_key=True)
    operator_account_id = Column(
        String(36),
        ForeignKey("operator_accounts.id"),
        nullable=False,
        index=True,
        default=DEFAULT_ACCOUNT_ID,
    )
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

    __table_args__ = (
        UniqueConstraint("id", "operator_account_id", name="uq_owner_profiles_owner"),
    )


class ProxyModel(Base):
    __tablename__ = "proxies"

    id = Column(String(36), primary_key=True)
    operator_account_id = Column(
        String(36),
        ForeignKey("operator_accounts.id"),
        nullable=False,
        index=True,
        default=DEFAULT_ACCOUNT_ID,
    )
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
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("id", "operator_account_id", name="uq_proxies_owner"),
    )


class BatchJobModel(Base):
    __tablename__ = "batch_jobs"

    id = Column(String(36), primary_key=True)
    operator_account_id = Column(
        String(36),
        ForeignKey("operator_accounts.id"),
        nullable=False,
        index=True,
        default=DEFAULT_ACCOUNT_ID,
    )
    name = Column(String(255), nullable=False)
    owner_profile_id = Column(String(36), ForeignKey("owner_profiles.id"), nullable=False)
    preferred_country = Column(String(10), nullable=True)
    concurrency = Column(Integer, default=2)
    delay_min = Column(Integer, default=30)
    delay_max = Column(Integer, default=90)
    status = Column(String(20), default="PENDING")
    execution_run_version = Column(Integer, nullable=False, default=1)
    pause_reason = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    owner_profile = relationship("OwnerProfileModel", back_populates="jobs")
    tasks = relationship(
        "ReportTaskModel",
        back_populates="batch_job",
        cascade="all, delete-orphan",
        foreign_keys="ReportTaskModel.batch_job_id",
    )

    __table_args__ = (
        UniqueConstraint("id", "operator_account_id", name="uq_batch_jobs_owner"),
    )


from app.infrastructure.persistence.task_models import (
    ReportTaskModel,
    TaskExecutionSlotModel,
    TaskStartReceiptModel,
    TaskControlReceiptModel,
    TaskArtifactLinkModel,
)
