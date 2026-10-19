# File: backend/app/infrastructure/persistence/repositories/control_repo.py
"""SQLAlchemy implementation of IControlRepository for task controls."""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import delete, select, update
from app.domain.exceptions.task_errors import StaleVersionError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.ports.task_execution_ports import IControlRepository
from app.domain.value_objects.task_execution import (
    ControlReceipt,
    ControlReceiptStatus,
    ControlTargetKind,
)
from app.infrastructure.persistence.task_models import TaskControlReceiptModel


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class SqlControlRepository(IControlRepository):
    def __init__(self, session: AsyncSession, operator_id: Optional[UUID] = None) -> None:
        self._session = session
        self._operator_id = operator_id

    def _owner(self, owner: UUID) -> None:
        if self._operator_id is not None and owner != self._operator_id:
            raise StaleVersionError("Control owner does not match transaction scope.")

    async def get_owned(
        self, owner: UUID, id: UUID
    ) -> Optional[ControlReceipt]:
        self._owner(owner)
        stmt = select(TaskControlReceiptModel).where(
            TaskControlReceiptModel.operator_account_id == str(owner),
            TaskControlReceiptModel.command_id == str(id),
        )
        res = await self._session.execute(stmt)
        m = res.scalar_one_or_none()
        if not m:
            return None
        return ControlReceipt(
            command_id=UUID(m.command_id),
            operator_id=UUID(m.operator_account_id),
            target_kind=ControlTargetKind(m.kind),
            target_id=m.target_id,
            target_generation=m.target_generation,
            initiating_session_id=UUID(m.initiating_session_id),
            auth_version=m.auth_version,
            admitted_at=_ensure_utc(m.admitted_at) or datetime.now(timezone.utc),
            status=ControlReceiptStatus(m.status),
            result_code=m.result_code,
            completed_at=_ensure_utc(m.completed_at),
            version=m.version, authority_contract_version=m.authority_contract_version,
            payload_fingerprint=m.payload_fingerprint, expected_task_version=m.expected_task_version,
            attempt_id=UUID(m.attempt_id) if m.attempt_id else None,
        )

    async def insert(self, receipt: ControlReceipt) -> None:
        self._owner(receipt.operator_id)
        if receipt.authority_contract_version != 2:
            raise StaleVersionError("Legacy control receipts are read-only.")
        model = TaskControlReceiptModel(
            command_id=str(receipt.command_id),
            operator_account_id=str(receipt.operator_id),
            kind=receipt.target_kind.value,
            target_id=receipt.target_id,
            target_generation=receipt.target_generation,
            initiating_session_id=str(receipt.initiating_session_id),
            auth_version=receipt.auth_version,
            admitted_at=receipt.admitted_at,
            status=receipt.status.value,
            result_code=receipt.result_code,
            completed_at=receipt.completed_at,
            version=receipt.version, authority_contract_version=receipt.authority_contract_version,
            payload_fingerprint=receipt.payload_fingerprint, expected_task_version=receipt.expected_task_version,
            attempt_id=str(receipt.attempt_id) if receipt.attempt_id else None,
        )
        self._session.add(model)
        await self._session.flush()

    async def _transition(self, owner: UUID, command_id: UUID, expected_version: int, status: ControlReceiptStatus, code: str) -> None:
        self._owner(owner)
        model = TaskControlReceiptModel
        result = await self._session.execute(update(model).where(
            model.operator_account_id == str(owner), model.command_id == str(command_id),
            model.version == expected_version, model.status == ControlReceiptStatus.ADMITTED.value,
            model.authority_contract_version == 2,
        ).values(status=status.value, result_code=code, version=expected_version + 1,
                 completed_at=datetime.now(timezone.utc)).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise StaleVersionError("Control receipt version conflict.")

    async def complete(self, owner: UUID, command_id: UUID, *, expected_version: int, result_code: str) -> None:
        await self._transition(owner, command_id, expected_version, ControlReceiptStatus.COMPLETE, result_code)

    async def mark_uncertain(self, owner: UUID, command_id: UUID, *, expected_version: int, reason: str) -> None:
        await self._transition(owner, command_id, expected_version, ControlReceiptStatus.RECOVERY_REQUIRED, reason)

    async def prune_completed(self, owner: UUID, before: datetime, limit: int) -> int:
        self._owner(owner)
        if limit <= 0:
            return 0
        model = TaskControlReceiptModel
        ids = select(model.command_id).where(model.operator_account_id == str(owner),
            model.status == ControlReceiptStatus.COMPLETE.value, model.completed_at < before).limit(min(limit, 1000))
        result = await self._session.execute(delete(model).where(model.operator_account_id == str(owner),
            model.status == ControlReceiptStatus.COMPLETE.value, model.command_id.in_(ids)))
        return result.rowcount
