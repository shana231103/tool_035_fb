# File: backend/app/infrastructure/automation/adspower_acquire.py
import asyncio
import logging
import time
from app.domain.exceptions.browser_errors import BrowserUnavailable
from app.domain.value_objects.browser_session import BrowserPhase, CleanupState, CompletionEvidence
from app.infrastructure.automation.adspower_wire import ProfileDraft, AdsPowerTransportError, TransportCertainty

logger = logging.getLogger(__name__)


async def drain_owned(task):
    """Repeated caller cancellation cannot detach finite owned provider work."""
    while True:
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            if task.cancelled():
                raise


class ProfileAcquireFlow:
    def __init__(self, client, ledger_factory, identity, budget, cdp, policy):
        self.client, self.identity, self.budget = client, identity, budget
        self.cdp, self.policy = cdp, policy
        self.cleanup = None
        self.operations = {}

    async def _create(self, record, request):
        await self.budget.transition(record.operation_id, BrowserPhase.CREATE_IN_FLIGHT)
        self.identity.assert_authority()
        draft = ProfileDraft(self.policy.settings.group_id, f"rpt_{record.operation_id}",
            self.identity.sign_marker(record.operation_id, record.marker_nonce), request.proxy)
        try:
            created = await self.client.create_profile(draft)
        except AdsPowerTransportError as error:
            if error.certainty == TransportCertainty.NOT_SENT:
                await self.budget.confirm_closed(record.operation_id, CompletionEvidence.NOT_CREATED)
            else:
                await self.budget.transition(record.operation_id, BrowserPhase.UNKNOWN_CREATE,
                    CleanupState.UNRESOLVED, safe_reason="BROWSER_CREATE_UNKNOWN")
            raise BrowserUnavailable(error.code, operation_id=record.operation_id) from None
        await self.budget.transition(record.operation_id, BrowserPhase.PROFILE_CREATED,
            newly_observed_profile_id=created.profile_id)
        return created

    async def run(self, request):
        record = await self.budget.reserve(request)
        try:
            async with asyncio.timeout(self.policy.settings.acquire_timeout):
                return await self._run_reserved(record, request)
        except TimeoutError:
            raise BrowserUnavailable("BROWSER_PROVIDER_UNAVAILABLE", operation_id=record.operation_id) from None

    async def _run_reserved(self, record, request):
        operation_id = record.operation_id
        stage = "create_profile"
        started_at = time.monotonic()
        task = asyncio.create_task(self._create(record, request))
        self.operations[operation_id] = task
        try:
            try:
                created = await asyncio.shield(task)
            except asyncio.CancelledError:
                await self.drain_create_result(operation_id, task)
                raise
            stage = "persist_start"
            await self.budget.transition(operation_id, BrowserPhase.START_IN_FLIGHT)
            self.identity.assert_authority()
            stage = "start_profile"
            start = asyncio.create_task(self.client.start_profile(created.profile_id))
            self.operations[operation_id] = start
            try:
                started = await asyncio.shield(start)
            except asyncio.CancelledError:
                try:
                    await drain_owned(start)
                except Exception:
                    started = None
                raise
            stage = "attach_cdp"
            attach = asyncio.create_task(self.cdp.attach(started, operation_id))
            self.operations[operation_id] = attach
            try:
                lease = await asyncio.shield(attach)
            except asyncio.CancelledError:
                try:
                    await drain_owned(attach)
                except Exception:
                    lease = None
                raise
            stage = "persist_attached"
            await self.budget.transition(operation_id, BrowserPhase.ATTACHED)
            return lease
        except BaseException as error:
            # Deliberately exclude exception text/tracebacks, profile IDs and endpoints.
            logger.warning("Browser acquire failed: stage=%s error_type=%s elapsed_seconds=%.1f",
                           stage, type(error).__name__, time.monotonic() - started_at)
            if self.cleanup is not None:
                cleanup = asyncio.create_task(self.cleanup.run(operation_id))
                self.operations[operation_id] = cleanup
                try:
                    await drain_owned(cleanup)
                except Exception:
                    cleanup = None
            if isinstance(error, asyncio.CancelledError):
                raise
            code = getattr(error, "code", "BROWSER_PROVIDER_UNAVAILABLE")
            raise BrowserUnavailable(code, operation_id=operation_id) from None
        finally:
            self.operations.pop(operation_id, None)

    async def drain_create_result(self, operation_id, task):
        try:
            await drain_owned(task)
        except Exception:
            return
