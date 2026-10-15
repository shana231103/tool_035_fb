# File: backend/app/infrastructure/mail/mailbox_connection_connect.py
import asyncio
import time

from app.application.mailbox_lifecycle import finish_owned
from app.domain.exceptions.mailbox_errors import MailboxError
from app.domain.value_objects.mailbox_credentials import MailboxAuthIdentity
from app.domain.value_objects.mailbox_verification import MailboxMapping, ReadBudget, normalize_email


class RefreshMailboxConnector:
    """Own the complete exchange/probe operation until publication or rollback."""

    def __init__(self, *, auth, registry, reservations, probe, template_version, connect_timeout=30):
        if not 0 < connect_timeout <= 30:
            raise ValueError("Invalid mailbox connect timeout")
        self.auth, self.registry, self.reservations = auth, registry, reservations
        self.probe, self.template_version = probe, template_version
        self.connect_timeout, self.tasks = connect_timeout, {}

    async def connect(self, connection_id, credentials):
        deadline = min(self.reservations.consume(connection_id), time.monotonic() + self.connect_timeout)
        generation = self.registry.get(connection_id).generation
        task = asyncio.create_task(self._run(connection_id, credentials, generation, deadline))
        self.tasks[connection_id] = task
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            self.cancel(connection_id)
            await finish_owned(self.rollback(connection_id))
            raise
        finally:
            if task.done() and self.tasks.get(connection_id) is task:
                self.tasks.pop(connection_id)

    def cancel(self, connection_id):
        self.reservations.cancel(connection_id)
        self.auth.revoke(connection_id)
        task = self.tasks.get(connection_id)
        if task and not task.done() and not task.cancelling():
            task.cancel()

    async def rollback(self, connection_id):
        task = self.tasks.get(connection_id)
        if task and task is not asyncio.current_task():
            await asyncio.gather(task, return_exceptions=True)
            if self.tasks.get(connection_id) is task:
                self.tasks.pop(connection_id)
        await self.auth.dispose(connection_id)
        record = self.registry.records.get(connection_id)
        if record and record.status == "disconnecting":
            record.mapping, record.initializing = None, False
            record.status, record.reason = "error", "DISCONNECTED"
            record.cleanup_complete = True

    async def _run(self, connection_id, credentials, generation, deadline):
        record = self.registry.get(connection_id)
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MailboxError("READ_BUDGET_EXHAUSTED")
            async with asyncio.timeout(remaining):
                await self.auth.import_credentials(connection_id, credentials, deadline)
                self.reservations.assert_current(connection_id, generation)
                identity = await self.probe.probe(connection_id, deadline=deadline,
                                                  budget=ReadBudget(10, 5, 1, deadline))
                self.reservations.assert_current(connection_id, generation)
                verified = self._identity(identity, credentials.email)
                mapping = MailboxMapping(verified.primary_email, verified.primary_email,
                    folders=("inbox", "junkemail"), template_version=self.template_version)
                if time.monotonic() >= deadline:
                    raise MailboxError("READ_BUDGET_EXHAUSTED")
                self._publish(record, verified, mapping)
                return self.registry.view(record)
        except BaseException as error:
            reason = error.reason if isinstance(error, MailboxError) else "MAILBOX_UNAVAILABLE"
            self.auth.revoke(connection_id)
            await finish_owned(self.auth.dispose(connection_id))
            record.mapping, record.initializing = None, False
            if record.status == "pending":
                record.status, record.reason = "error", reason
            record.cleanup_complete = True
            if isinstance(error, (MailboxError, asyncio.CancelledError)):
                raise
            raise MailboxError(reason) from None

    @staticmethod
    def _identity(identity, requested_email):
        if not isinstance(identity, dict):
            raise MailboxError("GRAPH_PROTOCOL_ERROR")
        provider_id = identity.get("id")
        mail = identity.get("mail")
        primary = identity.get("userPrincipalName") if mail is None or mail == "" else mail
        if not isinstance(provider_id, str) or not provider_id.strip() or not isinstance(primary, str):
            raise MailboxError("GRAPH_PROTOCOL_ERROR")
        primary = normalize_email(primary)
        if primary != requested_email:
            raise MailboxError("MAPPING_INVALID")
        return MailboxAuthIdentity(provider_id, primary)

    def _publish(self, record, identity, mapping):
        if self.template_version not in self.registry.evidence_versions:
            raise MailboxError("EVIDENCE_REQUIRED")
        self.auth.assert_active(record.id)
        for other in self.registry.records.values():
            if other.id != record.id and (
                    (other.status == "connected" and (other.account_id == identity.provider_user_id or
                     other.primary_email == identity.primary_email)) or
                    (other.mapping and other.mapping.meta_email == mapping.meta_email)):
                raise MailboxError("BUSY")
        self.auth.bind_identity(record.id, identity)
        record.primary_email, record.account_id = identity.primary_email, identity.provider_user_id
        record.mapping, record.revision = mapping, record.revision + 1
        record.status, record.reason, record.expires_at = "connected", None, None
        record.initializing = False
