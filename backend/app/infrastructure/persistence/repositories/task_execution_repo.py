# File: backend/app/infrastructure/persistence/repositories/task_execution_repo.py
"""Fenced singleton authority; release always rechecks the global resource ledger."""
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.exceptions.task_errors import TaskBusyError
from app.domain.ports.task_execution_ports import ITaskExecutionRepository
from app.domain.value_objects.task_execution import ExecutionGrant, ExecutionScope, ExecutionSlotRecord, RuntimeDrainProof, SlotPhase, SystemRecoveryProof
from app.infrastructure.persistence.task_models import TaskExecutionSlotModel as Slot, TaskStartReceiptModel
from app.infrastructure.persistence.repositories.browser_session_repo import BrowserSessionRepository


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class SqlTaskExecutionRepository(ITaskExecutionRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def read(self) -> ExecutionSlotRecord:
        result = await self._session.execute(select(Slot).where(Slot.singleton_id == 1).with_for_update().execution_options(populate_existing=True))
        m = result.scalar_one_or_none()
        if m is None:
            raise TaskBusyError("Execution slot schema is not initialized.")
        grant = None
        authority_version = 2
        if m.task_id:
            receipt = (await self._session.execute(select(TaskStartReceiptModel).where(
                TaskStartReceiptModel.operator_account_id == m.operator_account_id,
                TaskStartReceiptModel.command_id == m.command_id))).scalar_one_or_none()
            if receipt is None:
                raise TaskBusyError("Execution slot has no admission provenance.")
            authority_version = receipt.authority_contract_version
            if authority_version == 2:
                grant = ExecutionGrant(ExecutionScope(UUID(m.operator_account_id), UUID(m.task_id),
                    UUID(m.attempt_id), m.run_version, m.generation, UUID(m.runtime_epoch)),
                    UUID(m.command_id), _utc(m.admitted_at), receipt.admitted_task_version - 1)
            elif authority_version != 1:
                raise TaskBusyError("Unsupported slot admission authority contract.")
        return ExecutionSlotRecord(1, m.generation, SlotPhase(m.phase), grant,
            UUID(m.recovery_id) if m.recovery_id else None, m.recovery_reason,
            _utc(m.recovery_started_at) if m.recovery_started_at else None, authority_version)

    def _identity(self, grant):
        return (Slot.singleton_id == 1, Slot.generation == grant.slot_generation,
            Slot.task_id == str(grant.scope.task_id), Slot.operator_account_id == str(grant.scope.operator_id),
            Slot.attempt_id == str(grant.attempt_id), Slot.run_version == grant.run_version,
            Slot.command_id == str(grant.command_id), Slot.runtime_epoch == str(grant.runtime_epoch))

    async def _cas(self, predicates, **values):
        result = await self._session.execute(update(Slot).where(*predicates).values(**values).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise TaskBusyError("Execution slot authority conflict.")

    async def claim(self, grant: ExecutionGrant, expected_generation: int) -> None:
        if grant.slot_generation != expected_generation + 1:
            raise TaskBusyError("Grant must carry the post-claim generation.")
        await self._cas((Slot.singleton_id == 1, Slot.generation == expected_generation,
            Slot.phase == SlotPhase.FREE.value, Slot.task_id.is_(None), Slot.recovery_id.is_(None)),
            generation=grant.slot_generation, phase=SlotPhase.ADMITTED.value,
            task_id=str(grant.scope.task_id), operator_account_id=str(grant.scope.operator_id),
            attempt_id=str(grant.attempt_id), run_version=grant.run_version,
            command_id=str(grant.command_id), runtime_epoch=str(grant.runtime_epoch), admitted_at=grant.admitted_at)

    async def set_phase(self, grant, expected_phase, next_phase):
        allowed = {SlotPhase.ADMITTED: {SlotPhase.RUNNING, SlotPhase.DRAINING}, SlotPhase.RUNNING: {SlotPhase.DRAINING}}
        if next_phase not in allowed.get(expected_phase, set()):
            raise TaskBusyError("Invalid slot phase transition.")
        await self._cas((*self._identity(grant), Slot.phase == expected_phase.value), phase=next_phase.value)

    async def mark_recovery(self, grant, *, expected_generation, recovery_id, safe_code):
        predicates = self._identity(grant) if grant else (Slot.singleton_id == 1, Slot.generation == expected_generation)
        if grant is not None and grant.slot_generation != expected_generation:
            raise TaskBusyError("Recovery generation conflict.")
        await self._cas(predicates, phase=SlotPhase.RECOVERY_REQUIRED.value,
            recovery_id=str(recovery_id), recovery_reason=safe_code, recovery_started_at=datetime.now(timezone.utc))

    async def _ledger_clear(self):
        snapshot = await BrowserSessionRepository(self._session).read_bootstrap_snapshot()
        if not snapshot.complete or snapshot.total_charged or snapshot.unclosed_records:
            raise TaskBusyError("Global browser resource census is not clear.")
        return snapshot

    @staticmethod
    def _empty(generation):
        return dict(generation=generation, phase=SlotPhase.FREE.value, task_id=None,
            operator_account_id=None, attempt_id=None, run_version=None, command_id=None,
            runtime_epoch=None, admitted_at=None, recovery_id=None, recovery_reason=None, recovery_started_at=None)

    async def release(self, grant: ExecutionGrant, proof: RuntimeDrainProof) -> None:
        if ((proof.task_id, proof.attempt_id, proof.slot_generation, proof.runtime_epoch, proof.owner_id, proof.command_id)
                != (grant.scope.task_id, grant.attempt_id, grant.slot_generation, grant.runtime_epoch, grant.scope.operator_id, grant.command_id)
                or not all((proof.registration_closed, proof.callbacks_settled, proof.business_finalized, proof.ledger_complete, proof.ledger_clear))
                or proof.owned_remaining != 0 or not proof.census_id.int or proof.observed_at.tzinfo is None):
            raise TaskBusyError("Drain proof does not authorize release.")
        await self._ledger_clear()
        await self._cas((*self._identity(grant), Slot.phase.in_((SlotPhase.DRAINING.value, SlotPhase.RECOVERY_REQUIRED.value))),
                        **self._empty(grant.slot_generation + 1))

    async def clear_recovery(self, expected_generation, recovery_id, proof: SystemRecoveryProof):
        if (proof.recovery_id != recovery_id or proof.generation != expected_generation
                or not proof.prior_active_census_complete or proof.prior_active_census_count
                or not proof.ledger_complete or not proof.ledger_clear or not proof.census_id.int):
            raise TaskBusyError("System recovery proof is incomplete.")
        snapshot = await self._ledger_clear()
        if snapshot.binding is None or (snapshot.binding.installation_id, snapshot.binding.provider_binding_id) != (proof.installation_id, proof.provider_binding_id):
            raise TaskBusyError("Recovery installation binding mismatch.")
        await self._cas((Slot.singleton_id == 1, Slot.generation == expected_generation,
            Slot.phase == SlotPhase.RECOVERY_REQUIRED.value, Slot.recovery_id == str(recovery_id)),
            **self._empty(expected_generation + 1))
