# File: backend/app/application/owned_tasks.py
"""Strong task ownership with a sealed producer/child census."""
import asyncio
from contextvars import ContextVar
from uuid import UUID, uuid4

from app.application.task_runtime_records import OwnedCensus, OwnedTicket, OwnedWorkKind

current_ownership = ContextVar("task_execution_ownership", default=None)
current_stop_request = ContextVar("task_execution_stop_request", default=lambda: False)


class OwnedTasks:
    def __init__(self, runtime_epoch: UUID, attempt_id: UUID | None = None):
        self.runtime_epoch, self.attempt_id = runtime_epoch, attempt_id
        self._tasks: dict[OwnedTicket, tuple[OwnedWorkKind, asyncio.Task]] = {}
        self._closed = False
        self._sealed = False
        self._census_id = uuid4()
        self._callbacks = set()
        self._failed = False

    def register(self, kind, task, *, attempt_id, parent=None) -> OwnedTicket:
        live_parent = (parent in self._tasks and not self._tasks[parent][1].done())
        if self._sealed or (self._closed and not live_parent):
            raise RuntimeError("OWNERSHIP_REGISTRATION_CLOSED")
        if self.attempt_id is not None and attempt_id != self.attempt_id:
            raise ValueError("OWNERSHIP_ATTEMPT_MISMATCH")
        ticket = OwnedTicket(uuid4(), self.runtime_epoch, attempt_id)
        self._tasks[ticket] = (OwnedWorkKind(kind), task)
        self._callbacks.add(ticket)
        task.add_done_callback(lambda finished: self._settled(ticket, finished))
        return ticket

    def _settled(self, ticket, task):
        entry = self._tasks.get(ticket)
        failed = task.cancelled() or task.exception() is not None
        if entry and entry[0] not in (OwnedWorkKind.ADMISSION, OwnedWorkKind.CONTROL):
            self._failed = self._failed or failed
        self._callbacks.discard(ticket)
        self._tasks.pop(ticket, None)

    def close_registration(self):
        self._closed = True

    def retire_current(self, ticket):
        """Transfer the completed workflow's remaining lifetime to its runtime owner."""
        entry = self._tasks.get(ticket)
        if not self._closed or entry is None or entry[1] is not asyncio.current_task():
            raise RuntimeError("OWNERSHIP_TRANSFER_INVALID")
        del self._tasks[ticket]
        self._callbacks.discard(ticket)

    def snapshot(self) -> OwnedCensus:
        counts = tuple((kind, sum(k == kind and not t.done() for k, t in self._tasks.values()))
                       for kind in OwnedWorkKind)
        remaining = sum(count for _, count in counts)
        settled = not self._callbacks
        if self._closed and remaining == 0 and settled and not self._failed:
            self._sealed = True
        return OwnedCensus(self._census_id, self.runtime_epoch, self.attempt_id,
                           self._closed, counts, settled, self._sealed)

    async def join(self, deadline) -> OwnedCensus:
        loop = asyncio.get_running_loop()
        while True:
            census = self.snapshot()
            if census.complete or loop.time() >= deadline:
                return census
            pending = [task for _, task in self._tasks.values() if not task.done()]
            if not pending:
                await asyncio.sleep(0)  # Flush registered completion callbacks before sealing.
                return self.snapshot()
            await asyncio.wait(pending, timeout=max(0, deadline - loop.time()),
                               return_when=asyncio.FIRST_COMPLETED)
