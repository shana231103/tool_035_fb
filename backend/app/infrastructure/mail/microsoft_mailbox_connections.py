# File: backend/app/infrastructure/mail/microsoft_mailbox_connections.py
import asyncio
from uuid import uuid4
from app.application.mailbox_lifecycle import MailboxLocks, finish_owned

from app.domain.exceptions.mailbox_errors import MailboxError
from app.domain.ports.mailbox_code_reader import IMailboxConnections
from app.domain.value_objects.mailbox_verification import (
    DeviceLoginPrompt, MailboxBinding, MailboxConnectionView, MailboxMapping, normalize_email,
)


from .mailbox_registry import MailboxRecord


class MicrosoftMailboxConnections(IMailboxConnections):
    def __init__(self, auth, registry, probe, persistence=None):
        self.auth, self.registry, self.probe, self.persistence = auth, registry, probe, persistence
        self.closed = False
        self._synchronization = MailboxLocks(lambda _: self.registry.prune())
        self._completion_locks = self._synchronization.locks
        self.registry.operation_busy = self._synchronization.busy
        probe.connections = self

    async def restore_from_storage(self) -> int:
        if not self.persistence:
            return 0
        connections = self.persistence.load_all()
        if not connections:
            return 0
        restored = 0
        for conn_id, data in connections.items():
            if not isinstance(data, dict):
                continue
            account = data.get("account")
            token_cache = data.get("token_cache")
            account_id = data.get("account_id")
            primary_email = data.get("primary_email", "")
            if not conn_id or not account or not token_cache or not account_id:
                continue
            if conn_id in self.registry.records:
                continue
            if any(r.account_id == account_id and r.status == "connected" for r in self.registry.records.values()):
                continue
            try:
                self.auth.restore_state(conn_id, account, token_cache)
                record = MailboxRecord(
                    id=conn_id,
                    status="connected",
                    primary_email=normalize_email(primary_email),
                    account_id=account_id,
                    generation=1,
                    revision=0,
                    mapping=None,
                    expires_at=None,
                    reason=None,
                    cleanup_complete=False,
                    initializing=False,
                )
                self.registry.records[conn_id] = record

                mapping_data = data.get("mapping")
                if mapping_data and isinstance(mapping_data, dict):
                    meta_email = mapping_data.get("meta_email")
                    if meta_email:
                        mapping = MailboxMapping(
                            meta_email=meta_email,
                            primary_email=mapping_data.get("primary_email", record.primary_email),
                            confirmed_aliases=tuple(mapping_data.get("confirmed_aliases", ())),
                            folders=tuple(mapping_data.get("folders", ())),
                            template_version=mapping_data.get("template_version", "META_REPORT_V1"),
                        )
                        record.mapping = mapping
                        record.revision = max(1, int(data.get("revision", 1)))
                        if mapping.confirmed_aliases:
                            aliases = set(self.registry.verified_aliases.get(account_id, ()))
                            aliases.update(mapping.confirmed_aliases)
                            self.registry.verified_aliases[account_id] = tuple(aliases)
                restored += 1
            except Exception:
                continue
        return restored

    async def begin_login(self, account_hint: str | None = None) -> DeviceLoginPrompt:
        # A hint does not establish identity and is deliberately not used for mapping.
        if self.closed:
            raise MailboxError("DISCONNECTED")
        connection_id = str(uuid4())
        record = self.registry.reserve(connection_id)
        try:
            prompt = await self.auth.begin_device_login(connection_id)
            if self.closed or record.status != "pending":
                raise MailboxError("DISCONNECTED")
            record.expires_at = prompt.expires_at
            record.initializing = False
            return prompt
        except BaseException:
            await finish_owned(self._revoke(connection_id, "LOGIN_CANCELLED"))
            raise

    async def login_status(self, login_id: str) -> MailboxConnectionView:
        record = self.registry.get(login_id)
        async with self._synchronization.hold(login_id):
            await finish_owned(self._complete_login(record))
        return self.registry.view(record)

    async def _complete_login(self, record):
        login_id = record.id
        if record.initializing or record.status != "pending" or not self.auth.login_complete(login_id):
            return
        generation = record.generation
        try:
            account = self.auth.identity(login_id)
            account_id = account.get("home_account_id")
            if not account_id:
                raise MailboxError("AUTH_REQUIRED")
            self._check_duplicate(login_id, account_id)
            identity = await self.probe.probe(login_id)
            if generation != record.generation or record.status != "pending":
                raise MailboxError("DISCONNECTED")
            self._check_duplicate(login_id, account_id)
            record.primary_email = normalize_email(identity.get("mail") or identity.get("userPrincipalName", ""))
            record.account_id, record.status, record.expires_at = account_id, "connected", None
            if self.persistence is not None:
                try:
                    cache_str = self.auth.export_cache(login_id)
                    if cache_str:
                        self.persistence.save_connection(
                            connection_id=login_id,
                            account_id=account_id,
                            primary_email=record.primary_email,
                            account=account,
                            serialized_cache=cache_str,
                            mapping=record.mapping,
                            revision=record.revision,
                        )
                except Exception:
                    pass
        except Exception as error:
            if record.status == "pending":
                record.status = "error"
                record.reason = error.reason if isinstance(error, MailboxError) else "MAILBOX_UNAVAILABLE"
            await self.auth.cancel_login(login_id)
            record.cleanup_complete = True

    def _check_duplicate(self, login_id, account_id):
        if any(r.account_id == account_id and r.id != login_id and r.status == "connected"
               for r in self.registry.records.values()):
            raise MailboxError("BUSY")

    async def cancel_login(self, login_id: str) -> None:
        if self.persistence is not None:
            try:
                self.persistence.remove_connection(login_id)
            except Exception:
                pass
        await finish_owned(self._revoke(login_id, "LOGIN_CANCELLED"))

    async def list_connections(self) -> tuple[MailboxConnectionView, ...]:
        return tuple([await self.login_status(key) for key in tuple(self.registry.records)
                      if key in self.registry.records])

    async def set_mapping(self, connection_id: str, mapping: MailboxMapping) -> MailboxBinding:
        self.auth.identity(connection_id)
        binding = self.registry.set_mapping(connection_id, mapping)
        if self.persistence is not None:
            try:
                self.persistence.update_mapping(connection_id, mapping, binding.mapping_revision)
            except Exception:
                pass
        return binding

    async def resolve_binding(self, email: str) -> MailboxBinding:
        email = normalize_email(email)
        matches = [r for r in self.registry.records.values() if r.mapping and r.mapping.meta_email == email]
        if len(matches) != 1:
            raise MailboxError("MAPPING_INVALID")
        binding = self.registry.binding(matches[0])
        await self.assert_ready(binding)
        return binding

    async def assert_ready(self, binding: MailboxBinding) -> None:
        if self.closed:
            raise MailboxError("DISCONNECTED")
        self.registry.assert_current(binding)
        self.auth.identity(binding.connection_id)

    async def disconnect(self, connection_id: str) -> None:
        if self.persistence is not None:
            try:
                self.persistence.remove_connection(connection_id)
            except Exception:
                pass
        await finish_owned(self._revoke(connection_id, "DISCONNECTED"))

    async def _revoke(self, connection_id, reason):
        record = self.registry.records.get(connection_id)
        if record is None:
            return
        self.registry.revoke(connection_id)
        async with self._synchronization.hold(connection_id):
            await self.auth.cancel_login(connection_id)
            record.mapping = None
            record.status, record.reason = "error", reason
            record.cleanup_complete = True

    async def shutdown(self) -> None:
        self.closed = True
        for record in self.registry.records.values():
            self.registry.revoke(record.id)
        await finish_owned(self._shutdown())

    async def _shutdown(self):
        await asyncio.gather(*(self._revoke(key, "DISCONNECTED")
                               for key in tuple(self.registry.records)))
        await self.auth.shutdown()
        self.registry.records.clear()
