# File: backend/app/infrastructure/automation/adspower_budget.py
import asyncio
import secrets
from uuid import uuid4
from app.domain.exceptions.browser_errors import BrowserError, BrowserUnavailable, BrowserCleanupPending
from app.domain.value_objects.browser_session import (
    BrowserSessionRecord, BrowserSessionMutation, BrowserPhase, CleanupState, CompletionEvidence,
)


class BrowserResourceBudget:
    def __init__(self, ledger_factory, identity, policy):
        self.factory, self.identity, self.policy = ledger_factory, identity, policy
        self.condition = asyncio.Condition()
        self.validated = False

    async def snapshot(self):
        async with self.factory() as uow:
            return await uow.browser_sessions.read_bootstrap_snapshot()

    async def restore(self):
        snapshot = await self.snapshot()
        self.identity.verify_binding(snapshot.binding)
        if (not snapshot.complete or snapshot.total_charged != len(snapshot.unclosed_records)
                or any(not r.charged for r in snapshot.unclosed_records)):
            raise BrowserUnavailable("BROWSER_LEDGER_UNCERTAIN")
        for row in snapshot.unclosed_records:
            self.identity.verify_record(row)
        self.validated = True
        async with self.factory() as uow:
            return await uow.browser_sessions.summarize(self.identity.value.installation_id)

    async def get(self, operation_id):
        self.identity.assert_authority()
        async with self.factory() as uow:
            record = await uow.browser_sessions.get(operation_id)
        if record is None:
            raise LookupError("Browser operation not found")
        self.identity.verify_record(record)
        return record

    async def task_records(self, task_id):
        async with self.factory() as uow:
            return await uow.browser_sessions.get_unclosed_for_task(task_id)

    async def reserve(self, request):
        if not self.validated:
            raise BrowserUnavailable("BROWSER_LEDGER_UNCERTAIN")
        record = BrowserSessionRecord(uuid4(), self.identity.value.installation_id,
            self.identity.provider_binding_id, request.task_id, request.attempt_id, secrets.token_hex(16))
        try:
            async with asyncio.timeout(self.policy.settings.resource_wait_timeout):
                async with self.condition:
                    while True:
                        await self.restore()
                        if await self.task_records(request.task_id):
                            raise BrowserCleanupPending()
                        counts = await self.restore()
                        if counts.charged < self.policy.settings.max_profile_sessions:
                            await self._reserve_committed(record)
                            return record
                        await self.condition.wait()
        except TimeoutError:
            raise BrowserUnavailable("BROWSER_CAPACITY_WAIT") from None

    async def _reserve_committed(self, record):
        try:
            async with self.factory() as uow:
                await uow.browser_sessions.reserve(record, self.policy.settings.max_profile_sessions)
                await uow.commit()
        except Exception:
            try:
                observed = await self.get(record.operation_id)
            except Exception:
                raise BrowserUnavailable("BROWSER_LEDGER_UNCERTAIN", operation_id=record.operation_id) from None
            if observed != record:
                raise BrowserUnavailable("BROWSER_LEDGER_UNCERTAIN", operation_id=record.operation_id) from None

    async def mutate(self, record, mutation):
        self.identity.verify_record(record)
        changed = None
        try:
            async with self.factory() as uow:
                changed = await uow.browser_sessions.mutate(record.operation_id, record.version, mutation)
                await uow.commit()
            return changed
        except Exception:
            observed = await self.get(record.operation_id)
            if changed is not None and observed == changed:
                return observed
            raise BrowserUnavailable("BROWSER_LEDGER_UNCERTAIN", operation_id=record.operation_id) from None

    async def transition(self, operation_id, phase, cleanup=None, **kwargs):
        record = await self.get(operation_id)
        return await self.mutate(record, BrowserSessionMutation(phase, cleanup or record.cleanup_state, **kwargs))

    async def confirm_closed(self, operation_id, evidence, *, audit_reference=None, expected_version=None):
        if evidence == CompletionEvidence.UNKNOWN:
            raise BrowserError("BROWSER_LEDGER_UNCERTAIN")
        record = await self.get(operation_id)
        if expected_version is not None and record.version != expected_version:
            raise BrowserError("BROWSER_LEDGER_CONFLICT")
        if record.phase != BrowserPhase.CLOSED:
            await self.mutate(record, BrowserSessionMutation(BrowserPhase.CLOSED, CleanupState.CONFIRMED,
                completion_evidence=evidence, audit_reference=audit_reference))
        async with self.condition:
            self.condition.notify_all()
