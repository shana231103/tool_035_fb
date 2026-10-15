# File: backend/app/infrastructure/automation/adspower_cleanup.py
import asyncio
from app.domain.value_objects.browser_session import BrowserPhase, CleanupState, CompletionEvidence
from app.domain.value_objects.browser_status import CleanupOutcome, CleanupOutcomeState, CleanupConfirmation
from app.infrastructure.automation.adspower_acquire import drain_owned
from app.infrastructure.automation.adspower_wire import AdsPowerTransportError


class ProfileCleanupFlow:
    def __init__(self, client, ledger_factory, identity, budget, cdp, policy):
        self.client, self.identity, self.budget = client, identity, budget
        self.cdp, self.policy = cdp, policy
        self.operations = {}
        self.locks = {}

    async def run(self, operation_id):
        task = self.operations.get(operation_id)
        if task is None:
            task = asyncio.create_task(self._coordinated(operation_id))
            self.operations[operation_id] = task
        try:
            return await drain_owned(task)
        finally:
            if task.done() and self.operations.get(operation_id) is task:
                self.operations.pop(operation_id, None)

    async def _coordinated(self, operation_id):
        async with self.locks.setdefault(operation_id, asyncio.Lock()):
            return await self._attempt(operation_id)

    async def _attempt(self, operation_id):
        record = await self.budget.get(operation_id)
        if record.phase == BrowserPhase.CLOSED:
            confirmation = {CompletionEvidence.NOT_CREATED: CleanupConfirmation.NOT_CREATED,
                CompletionEvidence.DELETE_ACK: CleanupConfirmation.ACKNOWLEDGED,
                CompletionEvidence.EXTERNAL: CleanupConfirmation.EXTERNAL}[record.completion_evidence]
            return CleanupOutcome(operation_id, CleanupOutcomeState.CLOSED, confirmation=confirmation)
        if record.profile_id is None:
            if record.phase == BrowserPhase.RESERVED:
                await self.budget.confirm_closed(operation_id, CompletionEvidence.NOT_CREATED)
                return CleanupOutcome(operation_id, CleanupOutcomeState.CLOSED,
                                      confirmation=CleanupConfirmation.NOT_CREATED)
            if record.phase == BrowserPhase.CREATE_IN_FLIGHT:
                record = await self.budget.transition(operation_id, BrowserPhase.UNKNOWN_CREATE,
                    CleanupState.UNRESOLVED, safe_reason="BROWSER_CREATE_UNKNOWN")
            await self.budget.transition(operation_id, BrowserPhase.NEEDS_OPERATOR,
                CleanupState.UNRESOLVED, safe_reason="BROWSER_CREATE_UNKNOWN")
            return CleanupOutcome(operation_id, CleanupOutcomeState.UNRESOLVED, "BROWSER_CREATE_UNKNOWN")
        delete_dispatched = False
        try:
            async with asyncio.timeout(self.policy.settings.cleanup_timeout):
                if record.phase in {BrowserPhase.STOP_CONFIRMED, BrowserPhase.DELETE_IN_FLIGHT}:
                    await self.budget.transition(operation_id, BrowserPhase.CLEANUP_PENDING, CleanupState.PENDING)
                await self.budget.transition(operation_id, BrowserPhase.RELEASING, CleanupState.RUNNING)
                try:
                    await self.cdp.close_operation(operation_id)
                except AdsPowerTransportError:
                    # Stop/delete still owns the exact profile despite a failed local detach.
                    await asyncio.sleep(0)
                self.identity.assert_authority()
                status = await self.client.profile_status(record.profile_id)
                if status.active:
                    self.identity.assert_authority()
                    ack = await self.client.stop_profile(record.profile_id)
                    if not ack.acknowledged:
                        raise AdsPowerTransportError()
                await self.budget.transition(operation_id, BrowserPhase.STOP_CONFIRMED, CleanupState.RUNNING)
                await self.budget.transition(operation_id, BrowserPhase.DELETE_IN_FLIGHT, CleanupState.RUNNING)
                self.identity.assert_authority()
                delete_dispatched = True
                ack = await self.client.delete_profile(record.profile_id)
                if not ack.acknowledged:
                    raise AdsPowerTransportError()
                await self.budget.confirm_closed(operation_id, CompletionEvidence.DELETE_ACK)
                return CleanupOutcome(operation_id, CleanupOutcomeState.CLOSED,
                                      confirmation=CleanupConfirmation.ACKNOWLEDGED)
        except Exception:
            phase = BrowserPhase.DELETE_UNKNOWN if delete_dispatched else BrowserPhase.CLEANUP_PENDING
            retries = record.retries + 1
            state = CleanupState.RETRY_EXHAUSTED if retries >= self.policy.settings.cleanup_attempts else CleanupState.PENDING
            await self.budget.transition(operation_id, phase, state,
                safe_reason="BROWSER_CLEANUP_PENDING", retry_count=retries)
            return CleanupOutcome(operation_id, CleanupOutcomeState.PENDING, "BROWSER_CLEANUP_PENDING")
