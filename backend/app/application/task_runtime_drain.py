# File: backend/app/application/task_runtime_drain.py
"""Release only after sealed execution ownership and a fresh global ledger census."""
from uuid import uuid4

from app.application.task_drain_diagnostics import drain_stage, emit_drain
from app.application.task_runtime_records import DrainOutcome, ReleaseResolution
from app.domain.value_objects.enums import TaskStatus
from app.domain.value_objects.task_execution import RuntimeDrainProof, SlotPhase, StartOutcome


class TaskRuntimeDrainer:
    def __init__(self, factory, resources, authority, clock):
        self._factory, self._resources, self._authority, self._clock = factory, resources, authority, clock

    async def drain(self, grant, census, deadline):
        try:
            with drain_stage("DRAIN_SCOPE_EXIT", grant):
                async with self._factory.execution(grant) as uow:
                    with drain_stage("DRAIN_PHASE_WRITE", grant):
                        await uow.slot.set_phase(grant, SlotPhase.RUNNING, SlotPhase.DRAINING)
                    with drain_stage("DRAIN_RECEIPT_WRITE", grant):
                        await uow.start_receipts.set_outcome(grant.scope.operator_id, grant.command_id,
                                                            StartOutcome.RUNNING, StartOutcome.DRAINING)
                    with drain_stage("DRAIN_COMMIT", grant):
                        await uow.commit()
            with drain_stage("DRAIN_CENSUS", grant):
                closed = await census.join(deadline)
            emit_drain("DRAIN_CENSUS", grant=grant, census=closed)
            if not closed.complete:
                return await self._blocked(grant, "OWNED_DRAIN_UNKNOWN")
            with drain_stage("DRAIN_RESOURCE_CHECK", grant):
                await self._resources.assert_task_retriable(grant.scope.task_id)
            proof = await self._prove(grant, closed)
            resolution = await self.reconcile_release(grant, proof)
            emit_drain("RELEASE_READBACK", grant=grant, resolution=resolution)
            if resolution == ReleaseResolution.CONFIRMED_RELEASE:
                return DrainOutcome("RELEASED", "FINISHED", proof)
        except Exception:
            return await self._blocked(grant, "RESOURCE_DRAIN_UNKNOWN")
        return await self._blocked(grant, "RELEASE_OUTCOME_UNKNOWN")

    async def _prove(self, grant, census):
        with drain_stage("DRAIN_PROOF_SCOPE_EXIT", grant):
            async with self._factory.owned(grant.scope.operator_id) as uow:
                with drain_stage("DRAIN_PROOF_AUTHORITY", grant):
                    task = await self._authority.match_grant(uow, grant)
                emit_drain("DRAIN_PROOF_AUTHORITY", grant=grant, authority_match=True, task=task)
                with drain_stage("DRAIN_PROOF_LEDGER", grant):
                    ledger = await uow.browser_sessions.read_bootstrap_snapshot()
                emit_drain("DRAIN_PROOF_LEDGER", grant=grant, ledger=ledger)
        with drain_stage("DRAIN_PROOF_VALIDATE", grant):
            finalized = task.status in (TaskStatus.SUBMITTED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.NEEDS_REVIEW)
            clear = ledger.complete and not ledger.unclosed_records and not ledger.total_charged
            emit_drain("DRAIN_PROOF_VALIDATE", grant=grant, census=census, ledger=ledger,
                       task=task, business_finalized=finalized)
            if (not census.complete or census.runtime_epoch != grant.runtime_epoch
                    or census.attempt_id != grant.attempt_id or not census.registration_closed
                    or not census.callbacks_settled or census.remaining or not finalized or not clear):
                raise ValueError("RESOURCE_DRAIN_UNKNOWN")
        with drain_stage("DRAIN_PROOF_CREATE", grant):
            return RuntimeDrainProof(task_id=grant.scope.task_id, attempt_id=grant.attempt_id,
                slot_generation=grant.slot_generation, runtime_epoch=grant.runtime_epoch,
                owner_id=grant.scope.operator_id, command_id=grant.command_id, census_id=census.census_id,
                registration_closed=census.registration_closed, owned_remaining=census.remaining,
                callbacks_settled=census.callbacks_settled, business_finalized=finalized,
                ledger_complete=ledger.complete, ledger_clear=clear, observed_at=self._clock.now())

    async def reconcile_release(self, grant, proof):
        try:
            with drain_stage("RELEASE_SCOPE_EXIT", grant):
                async with self._factory.execution(grant) as uow:
                    with drain_stage("RELEASE_SLOT_WRITE", grant):
                        await uow.slot.release(grant, proof)
                    with drain_stage("RELEASE_RECEIPT_WRITE", grant):
                        await uow.start_receipts.set_outcome(grant.scope.operator_id, grant.command_id,
                                                            StartOutcome.DRAINING, StartOutcome.FINISHED)
                    with drain_stage("RELEASE_COMMIT", grant):
                        await uow.commit()
            return ReleaseResolution.CONFIRMED_RELEASE
        except Exception:
            try:
                with drain_stage("RELEASE_READ_SCOPE_EXIT", grant):
                    async with self._factory.owned(grant.scope.operator_id) as uow:
                        with drain_stage("RELEASE_READ_SLOT", grant):
                            slot = await uow.slot.read()
                        with drain_stage("RELEASE_READ_RECEIPT", grant):
                            receipt = await uow.start_receipts.get_owned(grant.scope.operator_id, grant.command_id)
                with drain_stage("RELEASE_READBACK", grant):
                    if (slot.is_free and slot.generation == grant.slot_generation + 1 and receipt
                            and receipt.attempt_id == grant.attempt_id and receipt.outcome_phase == StartOutcome.FINISHED):
                        return ReleaseResolution.CONFIRMED_RELEASE
                    return ReleaseResolution.NOT_RELEASED
            except Exception:
                return ReleaseResolution.UNKNOWN

    async def _blocked(self, grant, code):
        emit_drain("RECOVERY_MARK", grant=grant, recovery_reason=code)
        try:
            with drain_stage("RECOVERY_SCOPE_EXIT", grant):
                async with self._factory.execution(grant) as uow:
                    with drain_stage("RECOVERY_READ_SLOT", grant):
                        slot = await uow.slot.read()
                    if slot.grant == grant:
                        with drain_stage("RECOVERY_MARK", grant):
                            await uow.slot.mark_recovery(grant, expected_generation=grant.slot_generation,
                                                        recovery_id=uuid4(), safe_code=code)
                        with drain_stage("RECOVERY_READ_RECEIPT", grant):
                            receipt = await uow.start_receipts.get_owned(grant.scope.operator_id, grant.command_id)
                        with drain_stage("RECOVERY_RECEIPT_WRITE", grant):
                            await uow.start_receipts.set_outcome(grant.scope.operator_id, grant.command_id,
                                                                receipt.outcome_phase, StartOutcome.RECOVERY_REQUIRED)
                        with drain_stage("RECOVERY_COMMIT", grant):
                            await uow.commit()
        except Exception:
            return DrainOutcome("RECOVERY_REQUIRED", code)
        return DrainOutcome("RECOVERY_REQUIRED", code)
