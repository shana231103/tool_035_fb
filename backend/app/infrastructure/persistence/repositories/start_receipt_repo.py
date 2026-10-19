# File: backend/app/infrastructure/persistence/repositories/start_receipt_repo.py
"""SQLAlchemy implementation of ITaskStartReceiptRepository."""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.ports.task_execution_ports import ITaskStartReceiptRepository
from app.domain.value_objects.task_receipts import CurrentStartReceiptRecord, LegacyStartReceiptRecord, StartOutcome, StartReceiptRecord
from app.domain.exceptions.task_errors import StaleVersionError
from app.infrastructure.persistence.task_models import TaskStartReceiptModel


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class SqlTaskStartReceiptRepository(ITaskStartReceiptRepository):
    def __init__(self, session: AsyncSession, operator_id: Optional[UUID] = None) -> None:
        self._session = session
        self._operator_id = operator_id

    def _owner(self, owner: UUID) -> None:
        if self._operator_id is not None and self._operator_id != owner:
            raise StaleVersionError("Receipt owner does not match transaction scope.")

    async def get_owned(
        self, owner: UUID, command_id: UUID
    ) -> Optional[StartReceiptRecord]:
        self._owner(owner)
        stmt = select(TaskStartReceiptModel).where(
            TaskStartReceiptModel.operator_account_id == str(owner),
            TaskStartReceiptModel.command_id == str(command_id),
        )
        res = await self._session.execute(stmt)
        m = res.scalar_one_or_none()
        if not m:
            return None
        if m.authority_contract_version not in (1, 2):
            raise ValueError("Unsupported start receipt authority contract.")
        record_type = CurrentStartReceiptRecord if m.authority_contract_version == 2 else LegacyStartReceiptRecord
        return record_type(
            operator_id=UUID(m.operator_account_id),
            command_id=UUID(m.command_id),
            task_id=UUID(m.task_id),
            attempt_id=UUID(m.attempt_id),
            slot_generation=m.slot_generation,
            run_version=m.run_version,
            runtime_epoch=UUID(m.runtime_epoch),
            admitted_task_version=m.admitted_task_version,
            admitted_at=_ensure_utc(m.admitted_at) or datetime.now(timezone.utc),
            payload_fingerprint=m.payload_fingerprint,
            outcome_phase=m.outcome_phase,
        )

    async def insert(self, record: StartReceiptRecord) -> None:
        self._owner(record.operator_id)
        if record.authority_contract_version != 2:
            raise StaleVersionError("Legacy start receipts are read-only.")
        model = TaskStartReceiptModel(
            operator_account_id=str(record.operator_id),
            command_id=str(record.command_id),
            task_id=str(record.task_id),
            attempt_id=str(record.attempt_id),
            slot_generation=record.slot_generation,
            run_version=record.run_version,
            runtime_epoch=str(record.runtime_epoch),
            admitted_task_version=record.admitted_task_version,
            admitted_at=record.admitted_at,
            payload_fingerprint=record.payload_fingerprint,
            outcome_phase=record.outcome_phase.value,
            authority_contract_version=2,
        )
        self._session.add(model)
        await self._session.flush()

    async def set_outcome(self, owner: UUID, command_id: UUID, expected_phase: StartOutcome, next_phase: StartOutcome) -> None:
        self._owner(owner)
        expected_phase, next_phase = StartOutcome(expected_phase), StartOutcome(next_phase)
        allowed = {StartOutcome.ADMITTED: {StartOutcome.RUNNING, StartOutcome.DRAINING, StartOutcome.RECOVERY_REQUIRED},
                   StartOutcome.RUNNING: {StartOutcome.DRAINING, StartOutcome.RECOVERY_REQUIRED},
                   StartOutcome.DRAINING: {StartOutcome.FINISHED, StartOutcome.RECOVERY_REQUIRED},
                   StartOutcome.RECOVERY_REQUIRED: {StartOutcome.FINISHED}}
        if next_phase not in allowed.get(expected_phase, set()):
            raise StaleVersionError("Invalid start receipt outcome transition.")
        model = TaskStartReceiptModel
        result = await self._session.execute(update(model).where(
            model.operator_account_id == str(owner), model.command_id == str(command_id),
            model.authority_contract_version == 2, model.outcome_phase == expected_phase.value,
        ).values(outcome_phase=next_phase.value).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise StaleVersionError("Start receipt outcome conflict.")
