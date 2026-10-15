# File: backend/app/infrastructure/automation/adspower_recovery.py
import asyncio
from app.domain.value_objects.browser_session import BrowserPhase, CleanupState
from app.domain.value_objects.browser_status import BrowserReadiness, ReadinessState
from app.infrastructure.automation.adspower_binding_bootstrap import BrowserBindingBootstrap
from app.infrastructure.automation.adspower_wire import ProfileQuery


class BrowserRecovery:
    def __init__(self, client, ledger_factory, identity, budget, correlation, cleanup):
        self.client, self.factory, self.identity = client, ledger_factory, identity
        self.budget, self.correlation, self.cleanup = budget, correlation, cleanup
        self.binding_bootstrap = BrowserBindingBootstrap(ledger_factory, identity, budget, budget.policy.settings)
        self.failure = None
        self.classified = False
        self.closed = False

    async def bootstrap(self, *, maintenance=False):
        settings = self.budget.policy.settings
        if self.closed:
            return await self.readiness()
        if not settings.configured():
            self.failure = "BROWSER_NOT_CONFIGURED"
            return await self.readiness()
        try:
            await self.binding_bootstrap.prepare(maintenance=maintenance)
            if self.closed:
                return await self.readiness()
            if not maintenance:
                await self.client.list_profiles(ProfileQuery(settings.group_id, limit=1))
            self.classified = not self.closed
            self.failure = None
        except asyncio.CancelledError:
            self.classified = self.budget.validated = False
            self.identity.release()
            raise
        except Exception as error:
            self.classified = self.budget.validated = False
            self.failure = getattr(error, "code", "BROWSER_LEDGER_UNCERTAIN")
            self.identity.release()
        return await self.readiness()

    async def readiness(self):
        limit = self.budget.policy.settings.max_profile_sessions
        counts = None
        if self.classified:
            try:
                counts = await self.budget.restore()
            except Exception as error:
                self.failure = getattr(error, "code", "BROWSER_LEDGER_UNCERTAIN")
        if self.closed:
            return BrowserReadiness(ReadinessState.CLOSED, limit=limit, startup_classified=self.classified)
        if self.failure or not self.classified:
            return BrowserReadiness(ReadinessState.BLOCKED, limit=limit,
                safe_reason=self.failure or "BROWSER_LEDGER_UNCERTAIN", startup_classified=self.classified)
        available = counts.charged < limit
        state = ReadinessState.DEGRADED if counts.unclosed else ReadinessState.READY
        return BrowserReadiness(state, available, counts.charged, limit, counts.pending, counts.unknown,
            "BROWSER_CAPACITY_WAIT" if not available else None, True)

    async def retry(self, operation_id):
        record = await self.budget.get(operation_id)
        if record.phase in {BrowserPhase.UNKNOWN_CREATE, BrowserPhase.NEEDS_OPERATOR} and not record.profile_id:
            verdict = await self.correlation.find_candidate(record)
            if verdict.proved:
                await self.budget.transition(operation_id, BrowserPhase.PROFILE_CREATED,
                    newly_observed_profile_id=verdict.profile_id)
        return await self.cleanup.run(operation_id)

    async def reconcile(self, operation_id):
        settings = self.budget.policy.settings
        record = await self.budget.get(operation_id)
        if record.cleanup_state == CleanupState.RETRY_EXHAUSTED:
            return
        for delay in (0, 1, 3, 10)[:settings.cleanup_attempts]:
            record = await self.budget.get(operation_id)
            if record.cleanup_state == CleanupState.RETRY_EXHAUSTED:
                return
            if delay:
                await asyncio.sleep(delay)
            if self.closed:
                return
            result = await self.retry(operation_id)
            if result.state.value != "PENDING":
                return
