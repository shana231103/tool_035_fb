# File: backend/app/infrastructure/automation/adspower_session.py
import asyncio
from weakref import WeakValueDictionary
from app.domain.ports.browser_sessions import IBrowserControl
from app.domain.exceptions.browser_errors import BrowserUnavailable, BrowserCleanupPending, BrowserOwnershipError
from app.domain.value_objects.browser_session import CompletionEvidence
from app.domain.value_objects.browser_status import (
    BrowserStatus, BrowserTaskResourceStatus, TaskCleanupState, CleanupOutcome,
    CleanupOutcomeState, CleanupConfirmation,
)
from app.infrastructure.automation.adspower_acquire import drain_owned

class AdsPowerSessionService(IBrowserControl):
    def __init__(self, client, ledger_factory, identity, budget, cdp, acquire_flow,
                 cleanup_flow, recovery, policy, *, maintenance=False, schema_check=None):
        self.client, self.identity, self.budget, self.cdp = client, identity, budget, cdp
        self.acquire_flow, self.cleanup_flow, self.recovery, self.policy = acquire_flow, cleanup_flow, recovery, policy
        self.maintenance = maintenance
        self.schema_check = schema_check
        self.acquire_flow.cleanup = cleanup_flow
        self._bootstrap = None
        self._shutdown = None
        self._owners = set()
        self._handoffs = set()
        self._leases = WeakValueDictionary()
        self._active_leases = set()
        self._supervisors = {}
        self._reconcile_limit = asyncio.Semaphore(1)
        self._closing = False

    async def bootstrap(self):
        if self._bootstrap is None or (self._bootstrap.done() and not self.recovery.classified and not self._closing):
            self._bootstrap = asyncio.create_task(self._initialize())
        return await asyncio.shield(self._bootstrap)

    async def _initialize(self):
        if self._closing:
            return await self.recovery.readiness()
        if self.schema_check is not None:
            try:
                await self.schema_check()
            except Exception:
                self.recovery.failure = "BROWSER_LEDGER_UNCERTAIN"
                return await self.recovery.readiness()
        result = await self.recovery.bootstrap(maintenance=self.maintenance)
        if (result.startup_classified and result.state.value not in {"BLOCKED", "CLOSED"}
                and not self.maintenance and not self._closing):
            try:
                snapshot = await self.budget.snapshot()
            except Exception:
                self.recovery.failure = "BROWSER_LEDGER_UNCERTAIN"
                self.recovery.classified = self.budget.validated = False
                self.identity.release()
                return await self.recovery.readiness()
            for row in snapshot.unclosed_records:
                self._supervise(row.operation_id)
        return result

    def _supervise(self, operation_id):
        if self._closing:
            return
        previous = self._supervisors.get(operation_id)
        if previous is None or previous.done():
            task = asyncio.create_task(self._safe_reconcile(operation_id))
            self._supervisors[operation_id] = task

    async def _safe_reconcile(self, operation_id):
        try:
            async with self._reconcile_limit:
                await self.recovery.reconcile(operation_id)
        except Exception:
            self.recovery.failure = "BROWSER_LEDGER_UNCERTAIN"

    async def assert_ready(self):
        await self.bootstrap()
        readiness = await self.recovery.readiness()
        if self._closing or self.maintenance or not readiness.can_start:
            raise BrowserUnavailable(readiness.safe_reason or "BROWSER_NOT_CONFIGURED")

    async def assert_task_retriable(self, task_id):
        rows = await self.budget.task_records(task_id)
        if rows:
            raise BrowserCleanupPending(rows[0].operation_id)

    async def status(self, task_id=None):
        await self.bootstrap()
        resource = None
        if task_id is not None:
            rows = await self.budget.task_records(task_id)
            unknown = any(r.profile_id is None for r in rows)
            state = TaskCleanupState.UNRESOLVED if unknown else TaskCleanupState.PENDING if rows else TaskCleanupState.CLEAR
            resource = BrowserTaskResourceStatus(task_id, not rows, state,
                tuple(r.operation_id for r in rows), "BROWSER_CLEANUP_PENDING" if rows else None)
        return BrowserStatus(await self.recovery.readiness(), resource)

    async def acquire(self, request):
        await self.bootstrap()
        readiness = await self.recovery.readiness()
        if self._closing or self.maintenance or readiness.state.value not in {"READY", "DEGRADED"}:
            raise BrowserUnavailable(readiness.safe_reason or "BROWSER_NOT_CONFIGURED")
        handoff = asyncio.get_running_loop().create_future()
        self._handoffs.add(handoff)
        task = asyncio.create_task(self.acquire_flow.run(request))
        self._owners.add(task)
        try:
            lease = await asyncio.shield(task)
            self._leases[lease.operation_id] = lease
            if self._closing:
                await drain_owned(asyncio.create_task(self.cleanup_flow.run(lease.operation_id)))
                raise BrowserUnavailable("BROWSER_CLEANUP_PENDING")
            self._active_leases.add(lease.operation_id)
            return lease
        except asyncio.CancelledError:
            task.cancel()
            try:
                late_lease = await drain_owned(task)
                self._leases[late_lease.operation_id] = late_lease
                await drain_owned(asyncio.create_task(self.cleanup_flow.run(late_lease.operation_id)))
            except (Exception, asyncio.CancelledError):
                await asyncio.sleep(0)
            raise
        finally:
            self._owners.discard(task)
            handoff.set_result(None)
            self._handoffs.discard(handoff)

    async def release(self, lease):
        self.identity.assert_authority()
        if self._leases.get(lease.operation_id) is not lease:
            raise BrowserOwnershipError(operation_id=lease.operation_id)
        self._active_leases.discard(lease.operation_id)
        outcome = await self.cleanup_flow.run(lease.operation_id)
        if outcome.state == CleanupOutcomeState.PENDING and not self._closing:
            self._supervise(lease.operation_id)
        return outcome

    async def retry_cleanup(self, operation_id):
        await self.bootstrap()
        if self.maintenance or self._closing or not self.recovery.classified:
            raise BrowserUnavailable("BROWSER_NOT_CONFIGURED")
        handed_off = any(t.done() and not t.cancelled() and t.exception() is None
                         and t.result().operation_id == operation_id for t in self._owners)
        if operation_id in self.acquire_flow.operations or operation_id in self._active_leases or handed_off:
            raise BrowserCleanupPending(operation_id)
        return await self.recovery.retry(operation_id)

    async def confirm_external_cleanup(self, confirmation):
        await self.bootstrap()
        operation_id = confirmation.operation_id
        if (not self.maintenance or self._owners or operation_id in self.acquire_flow.operations
                or operation_id in self.cleanup_flow.operations
                or not confirmation.provider_mutation_terminal or not confirmation.confirmed_by_local_operator):
            raise BrowserOwnershipError(operation_id=operation_id)
        async with self.cleanup_flow.locks.setdefault(operation_id, asyncio.Lock()):
            await self.budget.confirm_closed(operation_id, CompletionEvidence.EXTERNAL,
                audit_reference=confirmation.audit_reference, expected_version=confirmation.expected_version)
        return CleanupOutcome(operation_id, CleanupOutcomeState.CLOSED, confirmation=CleanupConfirmation.EXTERNAL)

    async def shutdown(self):
        if self._shutdown is None or (self._shutdown.done() and (
                self._shutdown.cancelled() or self._shutdown.exception() is not None)):
            self._shutdown = asyncio.create_task(self._close())
        await drain_owned(self._shutdown)

    async def _close(self):
        self._closing = True
        self.recovery.closed = True
        for task in tuple(self._owners):
            task.cancel()
        tasks = tuple(self._owners) + tuple(self._supervisors.values()) + tuple(self.cleanup_flow.operations.values())
        tasks += tuple(self._handoffs)
        if self._bootstrap is not None:
            tasks += (self._bootstrap,)
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=self.policy.settings.shutdown_timeout)
            if pending:
                self.recovery.failure = "BROWSER_CLEANUP_PENDING"
                raise BrowserUnavailable("BROWSER_CLEANUP_PENDING")
        await self.cdp.shutdown()
        await self.client.aclose()
        self.identity.release()


def build_service(uow_factory, settings, *, max_sessions=None, maintenance=False, transport=None,
                  driver_factory=None, schema_check=None):
    from app.infrastructure.automation.adspower_composition import build_service as compose
    return compose(uow_factory, settings, max_sessions=max_sessions, maintenance=maintenance,
        transport=transport, driver_factory=driver_factory, schema_check=schema_check)
