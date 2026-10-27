# File: backend/app/application/dispatch_drain.py
import asyncio
from app.application.execution_context import (
    DrainConfirmed, DrainPending, RecoveredResourceHold, UnusedPermitConfirmed,
)
from app.application.dispatch_claim import restore_unstarted
from app.domain.value_objects.browser_session import BrowserPhase, CleanupState, CompletionEvidence
from app.domain.value_objects.mailbox_verification import normalize_email
from app.domain.value_objects.enums import TaskStatus


class DispatchDrain:
    def __init__(self, factory, budget, sessions, verification, browser=None, collector=None):
        self.factory, self.budget = factory, budget
        self.sessions, self.verification = sessions, verification
        self.browser, self.collector = browser, collector
        self.held = {}
        self._stop = asyncio.Event()
        self._observer = None

    async def bootstrap(self):
        if not self.browser:
            return
        status = await self.browser.status()
        if not status.readiness.startup_classified:
            raise ValueError("Browser resource census is not classified.")
        self.budget.limit_to(status.readiness.limit)
        async with self.factory() as uow:
            snapshot = await uow.browser_sessions.read_bootstrap_snapshot()
            if not snapshot.complete:
                raise ValueError("Browser resource census is incomplete.")
            holds = []
            for record in snapshot.unclosed_records:
                task = await uow.tasks.get_by_id(record.task_id)
                email = None
                if task and task.assignment:
                    email = task.assignment.assigned_mail_email
                elif task and task.attempt_id == str(record.attempt_id):
                    email = task.input_snapshot.get("owner_email")
                try:
                    email = normalize_email(email) if email else None
                except ValueError:
                    email = None
                holds.append(RecoveredResourceHold(record.operation_id, record.task_id,
                                                   str(record.attempt_id), email))
            if snapshot.total_charged > len(holds):
                raise ValueError("Charged browser resource census is incomplete.")
        permits = self.budget.seed_holds(tuple(holds))
        for permit, hold in zip(permits, holds):
            self.held[permit.id] = (permit, None, hold.operation_id)
        if self.held:
            self._ensure_observer()

    def _ensure_observer(self):
        if not self._stop.is_set() and (self._observer is None or self._observer.done()):
            self._observer = asyncio.create_task(self._observe())

    async def _resource_clear(self, permit, operation=None):
        if not self.browser:
            return True
        async with self.factory() as uow:
            snapshot = await uow.browser_sessions.read_bootstrap_snapshot()
            if not snapshot.complete:
                return False
            if operation:
                record = await uow.browser_sessions.get(operation)
                return bool(record and record.phase == BrowserPhase.CLOSED and not record.charged
                            and record.cleanup_state == CleanupState.CONFIRMED
                            and record.completion_evidence != CompletionEvidence.UNKNOWN)
        status = await self.browser.status(permit.task_id)
        return bool(status.readiness.startup_classified and status.task
                    and status.task.resource_allows_retry and not status.task.operation_refs)

    async def _confirm(self, permit, context=None, operation=None):
        if context:
            if self.collector:
                await self.collector.close(str(context.task_id), context.attempt_id)
            await self.verification.close(str(context.task_id))
            await self.sessions.unregister(str(context.task_id), context.attempt_id)
        if not await self._resource_clear(permit, operation):
            return False
        self.budget.release(permit, DrainConfirmed(permit.task_id, permit.id, True, True,
                                                  context.attempt_id if context else self.budget.attempt_for(permit)))
        return True

    async def finish(self, permit, context=None):
        try:
            if await self._confirm(permit, context):
                return
        except Exception:
            # A cleanup error is uncertainty, never a reason to free capacity.
            self.held[permit.id] = (permit, context, None)
        self.budget.hold_for_drain(permit, DrainPending(permit.task_id, permit.id))
        self.held[permit.id] = (permit, context, None)
        self._ensure_observer()

    def hold_unknown_claim(self, permit, context):
        if context:
            self.budget.bind_attempt(permit, context[0].attempt_id)
        self.budget.hold_for_drain(permit, DrainPending(permit.task_id, permit.id,
                                                     "ADMISSION_OUTCOME_UNKNOWN"))
        # Claim readback is required before any release, even if no browser row exists yet.
        self.held[permit.id] = (permit, context, "unknown-claim")
        self._ensure_observer()

    async def _resolve_claim(self, permit, record):
        if not record:
            return False
        context, claim = record
        async with self.factory() as uow:
            current = await uow.tasks.get_by_id(claim.task_id)
        if (not current or current.has_submission_evidence
                or current.status not in (TaskStatus.RUNNING, TaskStatus.QUEUED)):
            return False
        if self.collector:
            await self.collector.close(str(context.task_id), context.attempt_id)
        await self.verification.close(str(context.task_id))
        await self.sessions.unregister(str(context.task_id), context.attempt_id)
        state = "NOT_APPLIED"
        if current.attempt_id == claim.new_attempt_id:
            await restore_unstarted(self.factory, claim)
            state = "RESTORED_UNSTARTED"
        elif (current.status != TaskStatus.QUEUED
              or current.attempt_id != claim.expected_previous_attempt_id
              or current.dispatch_revision not in (claim.expected_dispatch_revision,
                                                    claim.expected_dispatch_revision + 2)):
            return False
        elif current.dispatch_revision == claim.expected_dispatch_revision + 2:
            state = "RESTORED_UNSTARTED"
        self.budget.release(permit, UnusedPermitConfirmed(permit.id, permit.task_id,
                                                         permit.budget_incarnation, state))
        return True

    async def poll_once(self):
        for key, (permit, context, operation) in tuple(self.held.items()):
            if operation == "unknown-claim":
                try:
                    if await self._resolve_claim(permit, context):
                        self.held.pop(key, None)
                except Exception:
                    continue
                continue
            try:
                if await self._confirm(permit, context, operation):
                    self.held.pop(key, None)
            except Exception:
                continue

    async def _observe(self):
        while not self._stop.is_set() and self.held:
            try:
                await asyncio.wait_for(self._stop.wait(), 5)
            except TimeoutError:
                await self.poll_once()

    async def shutdown(self):
        self._stop.set()
        if self._observer:
            await self._observer
