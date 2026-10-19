# File: backend/app/infrastructure/mail/mailbox_connection_reservations.py
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from app.domain.exceptions.mailbox_errors import MailboxError
from app.domain.value_objects.mailbox_credentials import MailboxConnectReservation


class MailboxConnectionReservations:
    """Empty, expiring single-consumer reservations; no credential state."""

    def __init__(self, *, registry, ttl_seconds=60, max_pending=2, max_pending_global=16, clock=time.monotonic):
        if not 0 < ttl_seconds <= 60 or not 1 <= max_pending <= 16:
            raise ValueError("Invalid mailbox reservation limits")
        self.registry, self.clock = registry, clock
        self.ttl_seconds, self.max_pending = ttl_seconds, max_pending
        self.max_pending_global = max_pending_global
        self._deadlines = {}
        self.closed = False

    def prune(self):
        for identifier, deadline in tuple(self._deadlines.items()):
            if deadline <= self.clock():
                self._deadlines.pop(identifier)
                record = self.registry.records.get(identifier)
                if record and record.status == "pending" and not record.initializing:
                    self.registry.records.pop(identifier)
        self.registry.prune()

    def reserve(self, owner: UUID | None = None, session_id: UUID | None = None):
        if self.closed:
            raise MailboxError("DISCONNECTED")
        self.prune()
        pending_records = [r for r in self.registry.records.values() if r.status == "pending"]
        if owner is not None:
            owner_pending = sum(getattr(r, "owner", None) == owner for r in pending_records)
            if owner_pending >= self.max_pending:
                raise MailboxError("BUSY")
            if len(pending_records) >= self.max_pending_global:
                raise MailboxError("BUSY")
        else:
            if len(pending_records) >= self.max_pending:
                raise MailboxError("BUSY")

        identifier = str(uuid4())
        record = self.registry.reserve(identifier, owner=owner, session_id=session_id)
        record.initializing = False
        record.expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.ttl_seconds)
        self._deadlines[identifier] = self.clock() + self.ttl_seconds
        return MailboxConnectReservation(identifier, record.expires_at, owner=owner, session_id=session_id)

    def consume(self, connection_id):
        self.prune()
        deadline = self._deadlines.pop(connection_id, None)
        record = self.registry.records.get(connection_id)
        if (self.closed or deadline is None or not record or record.status != "pending"
                or record.initializing):
            raise MailboxError("DISCONNECTED")
        record.initializing = True
        return deadline

    def assert_current(self, connection_id, generation):
        record = self.registry.get(connection_id)
        if self.closed or record.generation != generation or record.status != "pending":
            raise MailboxError("DISCONNECTED")

    def cancel(self, connection_id):
        self._deadlines.pop(connection_id, None)
        self.registry.revoke(connection_id)

    def cancel_pending_for_session(self, session_id: UUID):
        for identifier in tuple(self._deadlines):
            record = self.registry.records.get(identifier)
            if record and getattr(record, "session_id", None) == session_id and record.status == "pending":
                self._deadlines.pop(identifier, None)
                self.registry.revoke(identifier)

    def close(self):
        self.closed = True
        self._deadlines.clear()
