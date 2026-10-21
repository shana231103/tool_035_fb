# File: backend/app/infrastructure/persistence/repositories/operator_session_touch.py
"""Conditional session activity SQL shared by SQLite and PostgreSQL."""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import case, select, update

from app.infrastructure.persistence.operator_models import (
    OperatorAccountModel as Account, OperatorSessionModel as Session,
)


def touch_statement(
    id: UUID, expected_auth_version: int, now: datetime, min_interval: timedelta,
):
    if min_interval < timedelta(0):
        raise ValueError("Session touch interval must be nonnegative")
    candidate_idle = now + timedelta(minutes=30)
    extended_idle = case(
        (Session.idle_expires_at > candidate_idle, Session.idle_expires_at),
        else_=candidate_idle,
    )
    active_account = select(Account.id).where(
        Account.id == Session.operator_id,
        Account.status == "ACTIVE",
        Account.auth_version == expected_auth_version,
    ).exists()
    return (
        update(Session)
        .where(
            Session.id == str(id),
            Session.auth_version == expected_auth_version,
            Session.revoked_at.is_(None),
            Session.expires_at > now,
            Session.idle_expires_at > now,
            Session.last_seen_at <= now - min_interval,
            active_account,
        )
        .values(
            last_seen_at=now,
            idle_expires_at=case(
                (Session.expires_at < extended_idle, Session.expires_at),
                else_=extended_idle,
            ),
        )
        .execution_options(synchronize_session=False)
    )
