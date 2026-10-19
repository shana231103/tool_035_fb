# File: backend/app/infrastructure/persistence/repositories/operator_account_repo.py
"""SQLAlchemy repository for operator account persistence and write serialization."""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.operator_records import AccountMetadata
from app.domain.entities.operator_account import OperatorAccount
from app.domain.exceptions.operator_errors import OperatorError, StaleLoginProofError
from app.domain.ports.operator_security import IAccountRepository
from app.domain.value_objects.operator_identity import OperatorAccountStatus
from app.infrastructure.persistence.operator_models import OperatorAccountModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class SqlOperatorAccountRepository(IAccountRepository):
    """Postgres/SQLite repository for operator account management."""

    def __init__(self, session: AsyncSession):
        self._session = session

    def _to_entity(self, model: OperatorAccountModel) -> OperatorAccount:
        return OperatorAccount(
            id=UUID(model.id),
            username_key=model.username_key,
            username_display=model.username_display,
            password_hash=model.password_hash,
            status=OperatorAccountStatus(model.status),
            auth_version=model.auth_version,
            run_version=model.run_version,
            created_at=_ensure_utc(model.created_at),
            updated_at=_ensure_utc(model.updated_at),
        )

    async def find_login(self, username_key: str) -> Optional[OperatorAccount]:
        stmt = select(OperatorAccountModel).where(
            OperatorAccountModel.username_key == username_key
        )
        res = await self._session.execute(stmt)
        model = res.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get(self, id: UUID) -> Optional[OperatorAccount]:
        stmt = select(OperatorAccountModel).where(OperatorAccountModel.id == str(id))
        res = await self._session.execute(stmt)
        model = res.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def lock(self, id: UUID) -> OperatorAccount:
        stmt = select(OperatorAccountModel).where(
            OperatorAccountModel.id == str(id)
        ).with_for_update()
        res = await self._session.execute(stmt)
        model = res.scalar_one_or_none()
        if not model:
            raise OperatorError(f"Account {id} not found to lock")
        return self._to_entity(model)

    async def insert(self, account: OperatorAccount) -> None:
        model = OperatorAccountModel(
            id=str(account.id),
            username_key=account.username_key,
            username_display=account.username_display,
            password_hash=account.password_hash,
            status=account.status.value,
            auth_version=account.auth_version,
            run_version=account.run_version,
            created_at=account.created_at,
            updated_at=account.updated_at,
        )
        self._session.add(model)
        await self._session.flush()

    async def change_credentials(
        self, id: UUID, expected_version: int, encoded_hash: str
    ) -> None:
        stmt = (
            update(OperatorAccountModel)
            .where(
                OperatorAccountModel.id == str(id),
                OperatorAccountModel.auth_version == expected_version,
            )
            .values(
                password_hash=encoded_hash,
                auth_version=expected_version + 1,
                updated_at=_now(),
            )
        )
        res = await self._session.execute(stmt)
        if res.rowcount == 0:
            raise StaleLoginProofError("Credentials reset conflict: version stale")

    async def set_enabled(self, id: UUID, enabled: bool) -> None:
        acc = await self.get(id)
        if not acc:
            raise OperatorError(f"Account {id} not found")
        status_val = (
            OperatorAccountStatus.ACTIVE.value
            if enabled
            else OperatorAccountStatus.DISABLED.value
        )
        stmt = (
            update(OperatorAccountModel)
            .where(OperatorAccountModel.id == str(id))
            .values(
                status=status_val,
                auth_version=acc.auth_version + 1,
                run_version=acc.run_version + 1,
                updated_at=_now(),
            )
        )
        await self._session.execute(stmt)

    async def bump_auth_version(self, id: UUID) -> None:
        acc = await self.get(id)
        if not acc:
            raise OperatorError(f"Account {id} not found")
        stmt = (
            update(OperatorAccountModel)
            .where(OperatorAccountModel.id == str(id))
            .values(auth_version=acc.auth_version + 1, updated_at=_now())
        )
        await self._session.execute(stmt)

    async def list_metadata(self, limit: int, offset: int) -> List[AccountMetadata]:
        stmt = (
            select(OperatorAccountModel)
            .where(OperatorAccountModel.status != OperatorAccountStatus.QUARANTINED.value)
            .order_by(OperatorAccountModel.created_at)
            .limit(limit)
            .offset(offset)
        )
        res = await self._session.execute(stmt)
        models = res.scalars().all()
        return [
            AccountMetadata(
                id=UUID(m.id),
                username_display=m.username_display or m.username_key or "",
                status=OperatorAccountStatus(m.status),
                auth_version=m.auth_version,
                run_version=m.run_version,
                created_at=m.created_at,
                updated_at=m.updated_at,
            )
            for m in models
        ]
