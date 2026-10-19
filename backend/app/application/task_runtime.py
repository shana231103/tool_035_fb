# File: backend/app/application/task_runtime.py
"""Single-loop gated runtime. Admission never dispatches before durable commit."""
import asyncio
from uuid import uuid4

from app.application.owned_tasks import OwnedTasks, current_ownership, current_stop_request
from app.application.task_runtime_records import (
    AdmissionToken, OwnedWorkKind, RuntimeSnapshot, StagedHandle,
)
from app.domain.exceptions.task_errors import TaskAdmissionClosedError, TaskBusyError
from app.domain.value_objects.task_execution import SlotPhase, StartOutcome


class TaskRuntime:
    def __init__(self, factory, workflow, drainer, clock, runtime_epoch):
        self._factory, self._workflow, self._drainer = factory, workflow, drainer
        self._clock, self.runtime_epoch = clock, runtime_epoch
        self._token = None
        self._handle = None
        self._closed = False
        self._timed_out = False

    @property
    def is_busy(self):
        return self._token is not None

    def try_enter(self):
        if self._closed:
            raise TaskAdmissionClosedError("EXECUTION_UNAVAILABLE")
        if self.is_busy:
            raise TaskBusyError("EXECUTION_BUSY")
        self._token = AdmissionToken(uuid4(), self.runtime_epoch)
        self._timed_out = False
        return self._token

    def leave_unstaged(self, token):
        if self._token is token and self._handle is None:
            self._token = None

    def stage(self, token, grant):
        if self._closed or self._timed_out or token is not self._token or self._handle is not None:
            raise TaskBusyError("EXECUTION_BUSY")
        if grant.runtime_epoch != self.runtime_epoch:
            raise ValueError("EXECUTION_GRANT_MISMATCH")
        registry = OwnedTasks(self.runtime_epoch, grant.attempt_id)
        handle = StagedHandle(token, grant, asyncio.Event(), registry)
        task = asyncio.create_task(self._run_gated(handle))
        handle.task = task
        handle.ticket = registry.register(OwnedWorkKind.WORKFLOW, task,
                                          attempt_id=grant.attempt_id)
        self._handle = handle
        return handle

    def activate(self, staged):
        if self._handle is not staged or staged.state != "STAGED":
            raise TaskBusyError("EXECUTION_HANDLE_MISMATCH")
        staged.state = "ACTIVATING"
        staged.gate.set()

    async def abort_stage(self, staged):
        if self._handle is not staged or staged.state not in ("STAGED", "BLOCKED") or staged.gate.is_set():
            raise ValueError("EXECUTION_ABORT_UNSAFE")
        staged.state = "ABORTED"
        staged.gate.set()
        await asyncio.shield(staged.task)
        staged.registry.close_registration()
        await staged.registry.join(self._clock.monotonic() + 10)
        self._handle, self._token = None, None

    def retain_admission(self, token):
        if token is self._token:
            self._timed_out = True
            if self._handle:
                self._retain_blocked(self._handle, "START_OUTCOME_UNKNOWN")

    def _retain_blocked(self, handle, safe_code):
        handle.state, handle.safe_code = "BLOCKED", safe_code

    async def _run_gated(self, handle):
        await handle.gate.wait()
        if handle.state == "ABORTED":
            return
        grant = handle.grant
        try:
            async with self._factory.execution(grant) as uow:
                await uow.slot.set_phase(grant, SlotPhase.ADMITTED, SlotPhase.RUNNING)
                await uow.start_receipts.set_outcome(grant.scope.operator_id, grant.command_id,
                                                    StartOutcome.ADMITTED, StartOutcome.RUNNING)
                await uow.commit()
            handle.state = "ACTIVE"
            context = current_ownership.set((handle.registry, handle.ticket, grant.attempt_id))
            stop_context = current_stop_request.set(lambda: handle.stop_requested)
            try:
                await self._workflow(grant)
            finally:
                current_ownership.reset(context)
                current_stop_request.reset(stop_context)
            handle.state = "DRAINING"
            handle.registry.close_registration()
            handle.registry.retire_current(handle.ticket)
            outcome = await self._drainer.drain(grant, handle.registry,
                                                self._clock.monotonic() + 10)
            if outcome.state == "RELEASED":
                handle.state = "RELEASED"
                self._handle, self._token = None, None
            else:
                self._retain_blocked(handle, outcome.safe_code)
        except BaseException:
            self._retain_blocked(handle, "EXECUTION_RECOVERY_REQUIRED")

    def _request_stop(self, grant):
        handle = self._handle
        if handle is None:
            return None
        if handle.grant != grant:
            raise ValueError("EXECUTION_GRANT_MISMATCH")
        if handle.state == "STAGED":
            return None
        handle.stop_requested = True
        if handle.state == "ACTIVE" and not handle.task.done():
            handle.task.cancel()
        return handle

    async def stop_owned(self, grant):
        handle = self._request_stop(grant)
        if handle is None:
            return False
        done, _ = await asyncio.wait({handle.task}, timeout=10)
        return bool(done and handle.state == "RELEASED")

    def snapshot(self):
        h = self._handle
        return RuntimeSnapshot(self.runtime_epoch, not self._closed, self.is_busy,
                               bool(h and h.state == "BLOCKED"), h.state if h else "FREE",
                               h.grant if h else None)

    def close_admission(self):
        self._closed = True

    async def shutdown(self, deadline=None, *, timeout=10):
        self.close_admission()
        handle = self._handle
        if handle is None:
            return
        if handle.state == "STAGED":
            self._retain_blocked(handle, "START_OUTCOME_UNKNOWN")
            return
        handle.stop_requested = True
        if handle.state == "ACTIVE" and not handle.task.done():
            handle.task.cancel()
        remaining = max(0, (deadline or self._clock.monotonic() + timeout) - self._clock.monotonic())
        await asyncio.wait({handle.task}, timeout=remaining)
        if handle.state != "RELEASED":
            self._retain_blocked(handle, "SHUTDOWN_DRAIN_UNKNOWN")
