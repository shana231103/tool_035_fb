# File: backend/app/infrastructure/mail/microsoft_mailbox_connections.py
import asyncio

from app.application.mailbox_lifecycle import finish_owned
from app.domain.exceptions.mailbox_errors import MailboxError
from app.domain.ports.mailbox_code_reader import IMailboxConnections
from app.domain.value_objects.mailbox_verification import normalize_email
from .mailbox_connection_connect import RefreshMailboxConnector
from .mailbox_connection_reservations import MailboxConnectionReservations


class MicrosoftMailboxConnections(IMailboxConnections):
    def __init__(self, *, auth, registry, probe, template_version, reservations=None):
        self.auth, self.registry, self.probe = auth, registry, probe
        self.reservations = reservations or MailboxConnectionReservations(registry=registry)
        self.connector = RefreshMailboxConnector(auth=auth, registry=registry,
            reservations=self.reservations, probe=probe, template_version=template_version)
        self.closed = False
        self._cleanup = {}
        self.registry.operation_busy = lambda key: key in self.connector.tasks or key in self._cleanup
        probe.connections = self

    async def reserve_connection(self):
        if self.closed:
            raise MailboxError("DISCONNECTED")
        return self.reservations.reserve()

    async def connect(self, connection_id, credentials):
        if self.closed:
            raise MailboxError("DISCONNECTED")
        try:
            return await self.connector.connect(connection_id, credentials)
        finally:
            self.registry.prune()

    async def list_connections(self):
        self.reservations.prune()
        for record in self.registry.records.values():
            if record.status == "connected":
                try:
                    self.auth.assert_active(record.id)
                except MailboxError as error:
                    record.status, record.reason = "reauth_required", error.reason
        return tuple(self.registry.view(record) for record in self.registry.records.values())

    async def set_mapping(self, connection_id, mapping):
        self.auth.assert_active(connection_id)
        self.auth.identity(connection_id)
        return self.registry.set_mapping(connection_id, mapping)

    async def resolve_binding(self, email):
        email = normalize_email(email)
        matches = [r for r in self.registry.records.values() if r.mapping and r.mapping.meta_email == email]
        if len(matches) != 1:
            raise MailboxError("MAPPING_INVALID")
        binding = self.registry.binding(matches[0])
        await self.assert_ready(binding)
        return binding

    async def assert_ready(self, binding):
        if self.closed:
            raise MailboxError("DISCONNECTED")
        self.registry.assert_current(binding)
        self.auth.assert_active(binding.connection_id)
        self.auth.identity(binding.connection_id)

    def revoke(self, connection_id):
        self.connector.cancel(connection_id)

    async def disconnect(self, connection_id):
        self.revoke(connection_id)
        task = self._cleanup.get(connection_id)
        if task is None:
            task = asyncio.create_task(self._disconnect(connection_id))
            self._cleanup[connection_id] = task
        try:
            await finish_owned(asyncio.shield(task))
        finally:
            if task.done() and self._cleanup.get(connection_id) is task:
                self._cleanup.pop(connection_id)
                self.registry.prune()

    async def _disconnect(self, connection_id):
        await self.connector.rollback(connection_id)
        record = self.registry.records.get(connection_id)
        if record:
            record.mapping, record.initializing = None, False
            record.status, record.reason = "error", "DISCONNECTED"
            record.cleanup_complete = True

    async def shutdown(self):
        self.closed = True
        self.reservations.close()
        identifiers = tuple(self.registry.records)
        for identifier in identifiers:
            self.revoke(identifier)
        await finish_owned(self._shutdown(identifiers))

    async def _shutdown(self, identifiers):
        await asyncio.gather(*(self.disconnect(identifier) for identifier in identifiers))
        await self.auth.shutdown()
        self.registry.records.clear()
