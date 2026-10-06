# File: backend/app/application/mailbox_lifecycle.py
import asyncio
from contextlib import asynccontextmanager


async def finish_owned(awaitable):
    """Join owned cleanup despite repeated cancellation of its caller."""
    task = asyncio.ensure_future(awaitable)
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
        except Exception:
            break
    if cancelled:
        if not task.cancelled():
            task.exception()
        raise asyncio.CancelledError
    return task.result()


class MailboxLocks:
    """Count holders and queued waiters before any await; retire at zero."""

    def __init__(self, on_idle=None):
        self.locks = {}
        self._users = {}
        self.on_idle = on_idle or (lambda _: None)

    def busy(self, key):
        return key in self._users

    @asynccontextmanager
    async def hold(self, key):
        lock = self.locks.setdefault(key, asyncio.Lock())
        self._users[key] = self._users.get(key, 0) + 1
        try:
            async with lock:
                yield
        finally:
            users = self._users[key] - 1
            if users:
                self._users[key] = users
            else:
                self._users.pop(key)
                self.locks.pop(key)
                self.on_idle(key)
