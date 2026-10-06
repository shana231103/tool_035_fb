# File: backend/app/application/mailbox_sessions.py
import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable
from app.domain.exceptions.mailbox_errors import MailboxError
from app.domain.ports.mailbox_code_reader import IMailboxConnections
from app.domain.value_objects.mailbox_verification import MailboxBinding
from .mailbox_lifecycle import MailboxLocks, finish_owned


@dataclass
class _Attempt:
    binding: MailboxBinding
    task: asyncio.Task
    reason: str | None = None
    admitted: bool = False


class MailboxAttemptSessions:
    """The admission lock covers only readiness and the short durable transition."""

    def __init__(self, connections: IMailboxConnections | None = None):
        self.connections = connections
        self._attempts: dict[tuple[str, str], _Attempt] = {}
        self._revoked: set[str] = set()
        self._retiring: set[str] = set()
        self._synchronization = MailboxLocks(self._maybe_retire)
        self._locks = self._synchronization.locks
        self._closing = False

    def _maybe_retire(self, connection_id: str) -> None:
        if (connection_id in self._retiring and not self.is_connection_busy(connection_id)
                and not self._synchronization.busy(connection_id)):
            self._retiring.discard(connection_id)
            self._revoked.discard(connection_id)

    def retire_connection(self, connection_id: str) -> None:
        """Called only after backing auth and mapping have been revoked."""
        self._retiring.add(connection_id)
        self._maybe_retire(connection_id)

    def is_connection_busy(self, connection_id: str) -> bool:
        return any(a.binding.connection_id == connection_id for a in self._attempts.values())

    def register(self, task_id: str, attempt_id: str, binding: MailboxBinding,
                 task: asyncio.Task) -> None:
        if self._closing or binding.connection_id in self._revoked:
            raise MailboxError("DISCONNECTED")
        key = (task_id, attempt_id)
        if key in self._attempts:
            raise MailboxError("BUSY")
        self._attempts[key] = _Attempt(binding, task)

    async def assert_current(self, task_id: str, attempt_id: str,
                             binding: MailboxBinding) -> None:
        attempt = self._attempts.get((task_id, attempt_id))
        if (self._closing or not attempt or attempt.reason or attempt.binding != binding or
                binding.connection_id in self._revoked):
            raise MailboxError("DISCONNECTED")
        if not self.connections:
            raise MailboxError("AUTH_REQUIRED")
        await self.connections.assert_ready(binding)
        if (self._closing or self._attempts.get((task_id, attempt_id)) is not attempt
                or attempt.reason or binding.connection_id in self._revoked):
            raise MailboxError("DISCONNECTED")

    async def admit_submission(self, task_id: str, attempt_id: str,
                               persist_submitting: Callable[[], Awaitable[None]]) -> None:
        attempt = self._attempts.get((task_id, attempt_id))
        if not attempt:
            raise MailboxError("DISCONNECTED")
        async with self._synchronization.hold(attempt.binding.connection_id):
            await self.assert_current(task_id, attempt_id, attempt.binding)
            await persist_submitting()
            attempt.admitted = True

    async def invalidate_connection(self, connection_id: str, reason: str, *, caller=None) -> None:
        caller = caller or asyncio.current_task()
        await finish_owned(self._invalidate(connection_id, reason, caller))

    async def _invalidate(self, connection_id, reason, caller):
        async with self._synchronization.hold(connection_id):
            self._revoked.add(connection_id)
            targets = [a for a in self._attempts.values() if a.binding.connection_id == connection_id]
            for attempt in targets:
                already_cancelled = attempt.reason is not None
                attempt.reason = reason
                if not already_cancelled and attempt.task is not caller and not attempt.task.done():
                    attempt.task.cancel()
        # Never join a task under the admission lock it might need in finally.
        await asyncio.gather(*(a.task for a in targets if a.task is not caller),
                             return_exceptions=True)

    def cancellation_reason(self, task_id: str, attempt_id: str) -> str | None:
        attempt = self._attempts.get((task_id, attempt_id))
        return attempt.reason if attempt else None

    async def unregister(self, task_id: str, attempt_id: str) -> None:
        attempt = self._attempts.pop((task_id, attempt_id), None)
        if attempt:
            self._maybe_retire(attempt.binding.connection_id)

    async def shutdown(self) -> None:
        self._closing = True
        connections = {a.binding.connection_id for a in self._attempts.values()}
        for connection_id in connections:
            await self.invalidate_connection(connection_id, "DISCONNECTED")
