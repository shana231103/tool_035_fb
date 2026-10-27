# File: backend/app/infrastructure/automation/adspower_binding_bootstrap.py
import asyncio
from uuid import uuid4
from app.domain.exceptions.browser_errors import BrowserError, BrowserOwnershipError, BrowserUnavailable
from app.domain.value_objects.browser_status import RuntimeBinding
from app.infrastructure.automation.adspower_acquire import drain_owned


class BrowserBindingBootstrap:
    """Resolve durable provider authority before any provider work is admitted."""

    def __init__(self, uow_factory, identity, budget, settings, *, uuid_factory=uuid4):
        self.factory, self.identity, self.budget = uow_factory, identity, budget
        self.settings, self.uuid_factory = settings, uuid_factory
        self._expected = None
        self._children = set()

    async def _owned(self, operation):
        task = asyncio.create_task(operation)
        self._children.add(task)
        try:
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                try:
                    await drain_owned(task)
                except BaseException:
                    # Cancellation remains the caller's result after terminal work.
                    task.exception() if not task.cancelled() else None
                raise
        finally:
            self._children.discard(task)

    async def _identity_io(self, operation):
        return await self._owned(asyncio.to_thread(operation))

    def _allow_create(self, maintenance):
        configured = self.settings.initialize_identity
        return configured is True or (configured is None and not maintenance)

    @staticmethod
    def _validate_snapshot(snapshot):
        records = snapshot.unclosed_records
        if (not snapshot.complete or min(snapshot.total_ledger_rows, snapshot.total_charged) < 0
                or snapshot.total_ledger_rows < len(records)
                or snapshot.total_charged != len(records)
                or any(not record.charged for record in records)):
            raise BrowserUnavailable("BROWSER_LEDGER_UNCERTAIN")
        if snapshot.binding is None and (snapshot.total_ledger_rows or records or snapshot.total_charged):
            raise BrowserOwnershipError()

    def _load_identity(self, snapshot, allow_create):
        self.identity.assert_locked()
        try:
            self.identity.path.lstat()
        except FileNotFoundError:
            if not allow_create or snapshot.binding is not None or self._expected is not None:
                raise BrowserOwnershipError() from None
            return self.identity.initialize()
        except OSError:
            raise BrowserOwnershipError() from None
        return self.identity.load()

    async def _snapshot(self):
        async with self.factory() as uow:
            return await uow.browser_sessions.read_bootstrap_snapshot()

    def _assert_provider(self, binding):
        self.identity.verify_installation(binding)
        if (self.settings.provider_binding_id is not None
                and self.settings.provider_binding_id != binding.provider_binding_id):
            raise BrowserOwnershipError("PROVIDER_BINDING_MISMATCH")

    async def _resolve(self, *, allow_create):
        snapshot = await self._owned(self._snapshot())
        self._validate_snapshot(snapshot)
        await self._identity_io(lambda: self._load_identity(snapshot, allow_create))
        if self._expected is not None:
            self._assert_provider(self._expected)
            return await self._owned(self._readback(self._expected))
        if snapshot.binding is not None:
            self._assert_provider(snapshot.binding)
            return snapshot.binding
        if not allow_create:
            raise BrowserOwnershipError()
        value = self.identity.value
        self._expected = RuntimeBinding(value.installation_id,
            self.settings.provider_binding_id or self.uuid_factory(), value.host_binding_digest)
        return await self._persist(self._expected)

    async def _write_binding(self, expected):
        async with self.factory() as uow:
            await uow.browser_sessions.initialize_binding_if_empty(expected)

    async def _readback(self, expected):
        snapshot = await self._snapshot()
        self._validate_snapshot(snapshot)
        self.identity.verify_installation(expected)
        if snapshot.binding is None:
            self._expected = None  # Proven absent; only a later invocation may mint again.
            raise BrowserUnavailable("BROWSER_LEDGER_UNCERTAIN")
        if snapshot.binding != expected or snapshot.total_ledger_rows or snapshot.total_charged:
            raise BrowserUnavailable("BROWSER_LEDGER_UNCERTAIN")
        self._assert_provider(snapshot.binding)
        self._expected = None
        return snapshot.binding

    async def _persist(self, expected):
        async def write_and_observe():
            failure = None
            try:
                await self._write_binding(expected)
            except BaseException as error:
                failure = error
            # Context exit, including close, is terminal before opening a new UoW.
            observed = await self._readback(expected)
            if isinstance(failure, asyncio.CancelledError):
                raise failure
            return observed
        return await self._owned(write_and_observe())

    async def prepare(self, *, maintenance=False):
        self.budget.validated = False
        try:
            await self._identity_io(self.identity.acquire_lock)
            binding = await self._resolve(allow_create=self._allow_create(maintenance))
            self.identity.bind_provider(binding.provider_binding_id)
            await self._owned(self.budget.restore())
            return binding
        except BaseException as error:
            self.budget.validated = False
            try:
                await self._identity_io(self.identity.release)
            except Exception:
                if isinstance(error, asyncio.CancelledError):
                    raise error from None
                raise BrowserOwnershipError() from None
            if isinstance(error, (BrowserError, asyncio.CancelledError)):
                raise
            raise BrowserUnavailable("BROWSER_LEDGER_UNCERTAIN") from None
