# File: backend/app/application/use_cases/collect_email_verification_code.py
import asyncio
import secrets
import time
from uuid import uuid4
from app.domain.exceptions.mailbox_errors import MailboxError
from app.domain.ports.mailbox_code_reader import IEmailCodeCollector
from app.domain.value_objects.mailbox_verification import (
    AttemptMailLedger, AttemptReadContext, PreparedSend, ReadBudget, SendEpoch,
)
from app.application.mailbox_correlation import MailboxCorrelationPolicy
from app.application.mailbox_fresh_ownership import FreshMailboxOwnership
from app.application.mailbox_lifecycle import finish_owned


class CollectEmailVerificationCodeUseCase(IEmailCodeCollector):
    def __init__(self, connections, reader, submit_code, broker, sessions,
                 policy: MailboxCorrelationPolicy, clock=time.monotonic, *,
                 poll_interval: float = 5, max_requests: int = 160,
                 max_pages: int = 5, max_bodies: int = 20):
        if min(poll_interval, max_requests, max_pages, max_bodies) <= 0:
            raise ValueError("Collection limits must be positive.")
        self.connections, self.reader, self.submit_code = connections, reader, submit_code
        self.broker, self.sessions, self.policy, self.clock = broker, sessions, policy, clock
        self.poll_interval = poll_interval
        self.limits = (max_requests, max_pages, max_bodies)
        self.contexts, self.prepared, self.children, self.scanned = {}, {}, {}, {}
        self._fresh_ownership = FreshMailboxOwnership()

    async def assert_ready(self, binding) -> None:
        self.policy.assert_supported(binding.template_version)
        await self.connections.assert_ready(binding)

    def _attempt_context(self, task_id, attempt_id, deadline):
        key = (task_id, attempt_id)
        context = self.contexts.get(key)
        if context is None:
            requests, pages, bodies = self.limits
            context = AttemptReadContext(task_id, attempt_id,
                ReadBudget(requests, pages, bodies, deadline, self.clock),
                AttemptMailLedger(digest_key=secrets.token_bytes(32)))
            self.contexts[key] = context
        if context.budget.deadline != deadline:
            raise MailboxError("STALE")
        context.budget.check()
        return context

    async def prepare_send(self, binding, task_id, attempt_id, deadline):
        await self.assert_ready(binding)
        await self.sessions.assert_current(task_id, attempt_id, binding)
        key, lease, failed = (task_id, attempt_id), None, True
        if not self.policy.can_resend(binding.template_version):
            context = self.contexts.get(key)
            if context and context.ledger.send_epochs:
                raise MailboxError("CORRELATION_UNRESOLVED")
            lease = self._fresh_ownership.claim(key, binding)
        try:
            prepared = await self._prepare_send(binding, task_id, attempt_id, deadline)
            failed = False
            return prepared
        finally:
            if lease:
                if failed:
                    self.contexts.pop(key, None)
                    self.prepared.pop(key, None)
                self._fresh_ownership.finish_prepare(lease, failed)

    async def _prepare_send(self, binding, task_id, attempt_id, deadline):
        context = self._attempt_context(task_id, attempt_id, deadline)
        if context.ledger.send_epochs and context.ledger.send_epochs[-1].binding != binding:
            raise MailboxError("STALE")
        context.budget.page_remaining = self.limits[1]
        baseline = await self.reader.baseline(binding, context.budget)
        await self.sessions.assert_current(task_id, attempt_id, binding)
        if self.contexts.get((task_id, attempt_id)) is not context or not baseline.complete:
            raise MailboxError("CORRELATION_UNRESOLVED")
        prepared = PreparedSend(task_id, attempt_id, binding, baseline, deadline)
        self.prepared[(task_id, attempt_id)] = prepared
        return prepared

    async def mark_dispatched(self, prepared, observed_request_id):
        key = (prepared.task_id, prepared.attempt_id)
        requires_id = self.policy.requires_request_id(prepared.binding.template_version)
        pending = self.prepared.get(key)
        if (pending is None or prepared.baseline != pending.baseline or
                prepared.binding != pending.binding or prepared.deadline != pending.deadline or
                prepared.request_started_at is None or
                prepared.request_started_at < prepared.baseline.captured_at or
                (requires_id and not observed_request_id) or
                (not requires_id and observed_request_id is not None)):
            raise MailboxError("CORRELATION_UNRESOLVED")
        await self.sessions.assert_current(*key, prepared.binding)
        if self.prepared.get(key) is not pending:
            raise MailboxError("STALE")
        context = self._attempt_context(*key, prepared.deadline)
        if not requires_id:
            self._fresh_ownership.assert_current(key, prepared.binding)
            if context.ledger.send_epochs:
                raise MailboxError("CORRELATION_UNRESOLVED")
        if any(e.observed_request_id == observed_request_id for e in context.ledger.send_epochs):
            raise MailboxError("CORRELATION_AMBIGUOUS")
        epoch = SendEpoch(str(uuid4()), *key, prepared.binding, prepared.request_started_at,
            prepared.baseline.ids, prepared.deadline, observed_request_id)
        context.ledger.send_epochs.append(epoch)
        context.active_epoch_id = epoch.epoch_id
        context.budget.body_remaining = self.limits[2]
        self.prepared.pop(key, None)
        self.scanned[key] = set()
        return epoch

    async def assert_current(self, epoch):
        context = self.contexts.get((epoch.task_id, epoch.attempt_id))
        if context is None or context.active_epoch_id != epoch.epoch_id:
            raise MailboxError("STALE")
        context.budget.check()
        if not self.policy.requires_request_id(epoch.binding.template_version):
            self._fresh_ownership.assert_current((epoch.task_id, epoch.attempt_id), epoch.binding)
        await self.sessions.assert_current(epoch.task_id, epoch.attempt_id, epoch.binding)
        if (self.contexts.get((epoch.task_id, epoch.attempt_id)) is not context or
                context.active_epoch_id != epoch.epoch_id):
            raise MailboxError("STALE")
        context.budget.check()

    async def _scan(self, epoch):
        context = self.contexts[(epoch.task_id, epoch.attempt_id)]
        context.budget.page_remaining = self.limits[1]
        cursor, candidates, cursors = None, [], set()
        seen = self.scanned[(epoch.task_id, epoch.attempt_id)]
        while True:
            await self.assert_current(epoch)
            page = await self.reader.list_candidates(epoch, cursor, context.budget)
            await self.assert_current(epoch)
            for ref in page.refs:
                if ref.id in seen or ref.id in epoch.baseline_ids or ref.id in context.ledger.attempted_ids:
                    continue
                candidate = await self.reader.read_candidate(epoch.binding, ref, context.budget)
                await self.assert_current(epoch)
                seen.add(ref.id)
                if candidate is not None:
                    verdict = self.policy.decide(epoch, candidate, context.ledger)
                    if verdict.outcome == "ambiguous":
                        raise MailboxError("CORRELATION_AMBIGUOUS")
                    if verdict.outcome == "confirmed":
                        candidates.append(candidate)
            if page.next_cursor:
                if page.next_cursor in cursors:
                    raise MailboxError("GRAPH_PROTOCOL_ERROR")
                cursors.add(page.next_cursor)
                cursor = page.next_cursor
                continue
            if not page.complete:
                raise MailboxError("CORRELATION_UNRESOLVED")
            if len(candidates) > 1:
                raise MailboxError("CORRELATION_AMBIGUOUS")
            return candidates[0] if candidates else None

    async def collect(self, epoch, challenge_id) -> None:
        key = (epoch.task_id, epoch.attempt_id)
        if key in self.children:
            raise MailboxError("BUSY")
        child = asyncio.current_task()
        self.children[key] = child
        try:
            while True:
                await self.assert_current(epoch)
                await self.broker.assert_current(*key, challenge_id)
                candidate = await self._scan(epoch)
                if candidate is not None:
                    await self.assert_current(epoch)
                    await self.broker.assert_current(*key, challenge_id)
                    ledger = self.contexts[key].ledger
                    self.policy.record_attempted(ledger, candidate)
                    await self.submit_code.execute(*key, challenge_id, candidate.code)
                    ledger.consumed_ids.add(candidate.message_ref.id)
                    return
                await asyncio.sleep(min(self.poll_interval, max(0, epoch.deadline - self.clock())))
        finally:
            if self.children.get(key) is child:
                self.children.pop(key, None)

    async def close(self, task_id, attempt_id) -> None:
        await finish_owned(self._close(task_id, attempt_id, asyncio.current_task()))

    async def _close(self, task_id, attempt_id, caller):
        key = (task_id, attempt_id)
        lease = self._fresh_ownership.begin_close(key)
        if lease and lease.closer is not asyncio.current_task():
            await lease.closed.wait()
            return
        child = self.children.pop(key, None)
        self.contexts.pop(key, None)
        self.prepared.pop(key, None)
        self.scanned.pop(key, None)
        if child and child is not caller:
            child.cancel()
            await asyncio.gather(child, return_exceptions=True)
        await self._fresh_ownership.finish_close(lease)
