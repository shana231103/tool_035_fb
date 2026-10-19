# File: backend/app/application/task_recovery.py
"""Cold startup classifies old ownership conservatively and never resumes it."""
from dataclasses import dataclass
from uuid import UUID, uuid4

from app.application.unit_of_work import SystemPurpose
from app.domain.value_objects.enums import TaskStatus
from app.domain.value_objects.task_execution import SlotPhase


@dataclass(frozen=True)
class RecoveryView:
    status: str
    slot_phase: SlotPhase
    reconciled: bool
    recovery_id: UUID | None = None
    safe_code: str | None = None


class TaskRecoveryService:
    def __init__(self, factory, runtime, system_factory, clock):
        self._factory, self._runtime, self._system, self._clock = factory, runtime, system_factory, clock
        self._epoch = runtime.runtime_epoch

    async def classify_startup(self, runtime_epoch):
        if runtime_epoch != self._epoch:
            raise ValueError("RUNTIME_EPOCH_MISMATCH")
        return await self.reconcile_slot()

    async def reconcile_slot(self):
        async with self._system.open(SystemPurpose.RECOVERY) as uow:
            slot = await uow.slot.read()
            ledger = await uow.browser_sessions.read_bootstrap_snapshot()
            if slot.is_free and ledger.complete and not ledger.unclosed_records and not ledger.total_charged:
                return RecoveryView("HEALTHY", slot.phase, False)
            if slot.phase == SlotPhase.RECOVERY_REQUIRED:
                return RecoveryView("BLOCKED", slot.phase, False, slot.recovery_id, "RECOVERY_REQUIRED")
            recovery_id = uuid4()
            await uow.slot.mark_recovery(slot.grant, expected_generation=slot.generation,
                                        recovery_id=recovery_id, safe_code="COLD_START_RECOVERY_REQUIRED")
            await uow.commit()
        # Preserve SUBMITTED. An old possible-submit is never downgraded to retryable failure.
        if slot.grant:
            async with self._factory.execution(slot.grant) as uow:
                task = await uow.tasks.get_by_id(slot.task_id)
                if task and task.attempt_id == slot.attempt_id and task.status not in (
                        TaskStatus.SUBMITTED, TaskStatus.NEEDS_REVIEW, TaskStatus.FAILED, TaskStatus.CANCELLED):
                    version = task.version
                    task.mark_failed("COLD_START_RECOVERY_REQUIRED", retryable=False)
                    await uow.tasks.save(task, expected_version=version, expected_attempt_id=slot.attempt_id)
                    await uow.commit()
        return RecoveryView("BLOCKED", SlotPhase.RECOVERY_REQUIRED, False,
                            recovery_id, "RECOVERY_REQUIRED")

    async def clear_system_recovery(self, proof):
        snapshot = self._runtime.snapshot()
        if snapshot.busy or proof.runtime_epoch != self._epoch:
            raise ValueError("RECOVERY_CENSUS_INCOMPLETE")
        async with self._system.open(SystemPurpose.RECOVERY) as uow:
            await uow.slot.clear_recovery(proof.generation, proof.recovery_id, proof)
            await uow.commit()
        return await self.reconcile_slot()

    async def shutdown(self, deadline=None):
        self._runtime.close_admission()
