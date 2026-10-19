# File: backend/app/application/task_runtime_drain.py
"""Release only after sealed execution ownership and a fresh global ledger census."""
from uuid import uuid4

from app.application.task_runtime_records import DrainOutcome, ReleaseResolution
from app.domain.value_objects.enums import TaskStatus
from app.domain.value_objects.task_execution import RuntimeDrainProof, SlotPhase, StartOutcome


class TaskRuntimeDrainer:
    def __init__(self, factory, resources, authority, clock):
        self._factory, self._resources, self._authority, self._clock = factory, resources, authority, clock

    async def drain(self, grant, census, deadline):
        try:
            async with self._factory.execution(grant) as uow:
                await uow.slot.set_phase(grant, SlotPhase.RUNNING, SlotPhase.DRAINING)
                await uow.start_receipts.set_outcome(grant.scope.operator_id, grant.command_id,
                                                    StartOutcome.RUNNING, StartOutcome.DRAINING)
                await uow.commit()
            closed = await census.join(deadline)
            if not closed.complete:
                return await self._blocked(grant, "OWNED_DRAIN_UNKNOWN")
            await self._resources.assert_task_retriable(grant.scope.task_id)
            proof = await self._prove(grant, closed)
            resolution = await self.reconcile_release(grant, proof)
            if resolution == ReleaseResolution.CONFIRMED_RELEASE:
                return DrainOutcome("RELEASED", "FINISHED", proof)
        except Exception:
            return await self._blocked(grant, "RESOURCE_DRAIN_UNKNOWN")
        return await self._blocked(grant, "RELEASE_OUTCOME_UNKNOWN")

    async def _prove(self, grant, census):
        async with self._factory.owned(grant.scope.operator_id) as uow:
            task = await self._authority.match_grant(uow, grant)
            ledger = await uow.browser_sessions.read_bootstrap_snapshot()
        finalized = task.status in (TaskStatus.SUBMITTED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.NEEDS_REVIEW)
        clear = ledger.complete and not ledger.unclosed_records and not ledger.total_charged
        if (not census.complete or census.runtime_epoch != grant.runtime_epoch
                or census.attempt_id != grant.attempt_id or not census.registration_closed
                or not census.callbacks_settled or census.remaining or not finalized or not clear):
            raise ValueError("RESOURCE_DRAIN_UNKNOWN")
        return RuntimeDrainProof(task_id=grant.scope.task_id, attempt_id=grant.attempt_id,
            slot_generation=grant.slot_generation, runtime_epoch=grant.runtime_epoch,
            owner_id=grant.scope.operator_id, command_id=grant.command_id, census_id=census.census_id,
            registration_closed=census.registration_closed, owned_remaining=census.remaining,
            callbacks_settled=census.callbacks_settled, business_finalized=finalized,
            ledger_complete=ledger.complete, ledger_clear=clear, observed_at=self._clock.now())

    async def reconcile_release(self, grant, proof):
        try:
            async with self._factory.execution(grant) as uow:
                await uow.slot.release(grant, proof)
                await uow.start_receipts.set_outcome(grant.scope.operator_id, grant.command_id,
                                                    StartOutcome.DRAINING, StartOutcome.FINISHED)
                await uow.commit()
            return ReleaseResolution.CONFIRMED_RELEASE
        except Exception:
            try:
                async with self._factory.owned(grant.scope.operator_id) as uow:
                    slot = await uow.slot.read()
                    receipt = await uow.start_receipts.get_owned(grant.scope.operator_id, grant.command_id)
                if (slot.is_free and slot.generation == grant.slot_generation + 1 and receipt
                        and receipt.attempt_id == grant.attempt_id and receipt.outcome_phase == StartOutcome.FINISHED):
                    return ReleaseResolution.CONFIRMED_RELEASE
                return ReleaseResolution.NOT_RELEASED
            except Exception:
                return ReleaseResolution.UNKNOWN

    async def _blocked(self, grant, code):
        try:
            async with self._factory.execution(grant) as uow:
                slot = await uow.slot.read()
                if slot.grant == grant:
                    await uow.slot.mark_recovery(grant, expected_generation=grant.slot_generation,
                                                recovery_id=uuid4(), safe_code=code)
                    receipt = await uow.start_receipts.get_owned(grant.scope.operator_id, grant.command_id)
                    await uow.start_receipts.set_outcome(grant.scope.operator_id, grant.command_id,
                                                        receipt.outcome_phase, StartOutcome.RECOVERY_REQUIRED)
                    await uow.commit()
        except Exception:
            return DrainOutcome("RECOVERY_REQUIRED", code)
        return DrainOutcome("RECOVERY_REQUIRED", code)
