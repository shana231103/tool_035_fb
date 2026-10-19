# File: backend/app/infrastructure/persistence/operator_models.py
"""SQLAlchemy models for operator accounts and sessions."""

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from app.infrastructure.persistence.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class OperatorAccountModel(Base):
    __tablename__ = "operator_accounts"

    id = Column(String(36), primary_key=True)
    username_key = Column(String(64), nullable=True, unique=True, index=True)
    username_display = Column(String(64), nullable=True)
    password_hash = Column(String(255), nullable=True)
    status = Column(String(20), nullable=False, default="ACTIVE")
    auth_version = Column(Integer, nullable=False, default=1)
    run_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    sessions = relationship(
        "OperatorSessionModel",
        back_populates="account",
        cascade="all, delete-orphan",
    )


class OperatorSessionModel(Base):
    __tablename__ = "operator_sessions"

    id = Column(String(36), primary_key=True)
    secret_digest = Column(LargeBinary(32), nullable=False, unique=True, index=True)
    operator_id = Column(
        String(36), ForeignKey("operator_accounts.id"), nullable=False, index=True
    )
    auth_version = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)
    last_seen_at = Column(DateTime(timezone=True), default=_now)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    idle_expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    account = relationship("OperatorAccountModel", back_populates="sessions")
