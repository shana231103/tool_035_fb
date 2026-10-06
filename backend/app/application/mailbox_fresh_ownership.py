# File: backend/app/application/mailbox_fresh_ownership.py
import asyncio
from dataclasses import dataclass, field
from app.domain.exceptions.mailbox_errors import MailboxError
from app.domain.value_objects.mailbox_verification import normalize_email


@dataclass
class _Lease:
    key: tuple[str, str]
    email: str
    prepared: asyncio.Event = field(default_factory=asyncio.Event)
    closed: asyncio.Event = field(default_factory=asyncio.Event)
    closer: asyncio.Task | None = None
    closing: bool = False


class FreshMailboxOwnership:
    """Collector-local email ownership independent of queue/browser admission."""

    def __init__(self):
        self._emails, self._attempts = {}, {}

    def claim(self, key, binding):
        email = normalize_email(binding.meta_email)
        if email in self._emails or key in self._attempts:
            raise MailboxError("BUSY")
        lease = _Lease(key, email)
        self._emails[email] = self._attempts[key] = lease
        return lease

    def assert_current(self, key, binding):
        lease = self._attempts.get(key)
        if not lease or lease.closing or lease.email != normalize_email(binding.meta_email):
            raise MailboxError("STALE")

    def _release(self, lease):
        if self._attempts.get(lease.key) is lease:
            self._attempts.pop(lease.key)
        if self._emails.get(lease.email) is lease:
            self._emails.pop(lease.email)

    def finish_prepare(self, lease, failed):
        lease.prepared.set()
        if failed and not lease.closing:
            self._release(lease)

    def begin_close(self, key):
        lease = self._attempts.get(key)
        if lease and not lease.closing:
            lease.closing = True
            lease.closer = asyncio.current_task()
        return lease

    async def finish_close(self, lease):
        if lease:
            # A close during baseline must retain ownership until that read ends.
            await lease.prepared.wait()
            self._release(lease)
            lease.closed.set()
