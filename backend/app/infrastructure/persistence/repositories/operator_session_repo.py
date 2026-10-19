# File: backend/app/infrastructure/persistence/repositories/operator_session_repo.py
"""SQLAlchemy repository for operator session tracking, limits, touch, and pruning."""

from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple
from uuid import UUID
import sqlalchemy as sa
from sqlalchemy import case, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.ports.operator_security import ISessionRepository
from app.domain.value_objects.operator_identity import SessionRecord, SessionStatus
from app.infrastructure.persistence.operator_models import (
    OperatorAccountModel,
    OperatorSessionModel,
)


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class SqlOperatorSessionRepository(ISessionRepository):
    """Manages active, idle, capped, and revoked operator sessions."""

    def __init__(self, session: AsyncSession):
        self._session = session

    def _to_record(self, model: OperatorSessionModel) -> SessionRecord:
        return SessionRecord(
            id=UUID(model.id),
            secret_digest=model.secret_digest,
            operator_id=UUID(model.operator_id),
            auth_version=model.auth_version,
            created_at=_ensure_utc(model.created_at),
            last_seen_at=_ensure_utc(model.last_seen_at),
            expires_at=_ensure_utc(model.expires_at),
            idle_expires_at=_ensure_utc(model.idle_expires_at),
            revoked_at=_ensure_utc(model.revoked_at),
        )

    async def get_by_id(self, id: UUID) -> Optional[SessionRecord]:
        result = await self._session.execute(select(OperatorSessionModel).where(OperatorSessionModel.id == str(id)).execution_options(populate_existing=True))
        model = result.scalar_one_or_none()
        return self._to_record(model) if model else None

    async def get_by_digest(self, digest: bytes) -> Optional[SessionRecord]:
        stmt = select(OperatorSessionModel).where(
            OperatorSessionModel.secret_digest == digest
        )
        res = await self._session.execute(stmt)
        model = res.scalar_one_or_none()
        return self._to_record(model) if model else None

    async def insert(self, record: SessionRecord) -> None:
        now = record.created_at
        active_stmt = (
            select(OperatorSessionModel)
            .where(
                OperatorSessionModel.operator_id == str(record.operator_id),
                OperatorSessionModel.revoked_at.is_(None),
                OperatorSessionModel.expires_at > now,
                OperatorSessionModel.idle_expires_at > now,
            )
            .order_by(OperatorSessionModel.created_at.asc())
        )
        active_res = await self._session.execute(active_stmt)
        active_sessions = list(active_res.scalars().all())

        if len(active_sessions) >= 8:
            excess = len(active_sessions) - 7
            for s in active_sessions[:excess]:
                s.revoked_at = now

        model = OperatorSessionModel(
            id=str(record.id),
            secret_digest=record.secret_digest,
            operator_id=str(record.operator_id),
            auth_version=record.auth_version,
            created_at=record.created_at,
            last_seen_at=record.last_seen_at,
            expires_at=record.expires_at,
            idle_expires_at=record.idle_expires_at,
            revoked_at=record.revoked_at,
        )
        self._session.add(model)
        await self._session.flush()

    async def touch(self, id: UUID, expected_auth_version: int, now: datetime) -> bool:
        candidate_idle = now + timedelta(minutes=30)
        stmt = (
            update(OperatorSessionModel)
            .where(
                OperatorSessionModel.id == str(id),
                OperatorSessionModel.auth_version == expected_auth_version,
                OperatorSessionModel.revoked_at.is_(None),
                OperatorSessionModel.expires_at > now,
                OperatorSessionModel.idle_expires_at > now,
            )
            .values(
                last_seen_at=now,
                idle_expires_at=case(
                    (OperatorSessionModel.expires_at < candidate_idle, OperatorSessionModel.expires_at),
                    else_=candidate_idle,
                ),
            )
        )
        res = await self._session.execute(stmt)
        return res.rowcount > 0

    async def revoke(self, id: UUID, now: datetime) -> None:
        stmt = (
            update(OperatorSessionModel)
            .where(OperatorSessionModel.id == str(id))
            .values(revoked_at=now)
        )
        await self._session.execute(stmt)

    async def revoke_account(self, id: UUID, now: datetime) -> None:
        stmt = (
            update(OperatorSessionModel)
            .where(
                OperatorSessionModel.operator_id == str(id),
                OperatorSessionModel.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        await self._session.execute(stmt)

    async def list_valid(
        self, ids: Tuple[UUID, ...], now: datetime
    ) -> Dict[UUID, SessionStatus]:
        if not ids:
            return {}
        capped_ids = [str(i) for i in ids[:32]]

        stmt = (
            select(OperatorSessionModel, OperatorAccountModel)
            .outerjoin(
                OperatorAccountModel,
                OperatorSessionModel.operator_id == OperatorAccountModel.id,
            )
            .where(OperatorSessionModel.id.in_(capped_ids))
        )
        res = await self._session.execute(stmt)
        rows = {UUID(s.id): (s, a) for s, a in res.all()}

        statuses: Dict[UUID, SessionStatus] = {}
        for sess_id in ids[:32]:
            pair = rows.get(sess_id)
            if not pair or not pair[0]:
                statuses[sess_id] = SessionStatus.UNKNOWN
                continue
            sess, acc = pair
            if not acc or acc.status != "ACTIVE":
                statuses[sess_id] = SessionStatus.REVOKED
            elif sess.auth_version != acc.auth_version:
                statuses[sess_id] = SessionStatus.REVOKED
            elif sess.revoked_at is not None:
                statuses[sess_id] = SessionStatus.REVOKED
            elif now > _ensure_utc(sess.expires_at) or now > _ensure_utc(sess.idle_expires_at):
                statuses[sess_id] = SessionStatus.EXPIRED
            else:
                statuses[sess_id] = SessionStatus.VALID
        return statuses

    async def prune(self, before: datetime, limit: int) -> int:
        if limit <= 0:
            return 0
        subquery = (
            select(OperatorSessionModel.id)
            .where(
                (OperatorSessionModel.expires_at < before)
                | (OperatorSessionModel.revoked_at < before)
            )
            .order_by(OperatorSessionModel.created_at.asc())
            .limit(limit)
        )
        stmt = delete(OperatorSessionModel).where(OperatorSessionModel.id.in_(subquery))
        res = await self._session.execute(stmt)
        return res.rowcount or 0
