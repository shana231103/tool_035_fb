# File: backend/app/application/use_cases/manage_mailbox_connection.py
import asyncio
from app.application.mailbox_sessions import MailboxAttemptSessions
from app.application.mailbox_lifecycle import finish_owned
from app.domain.exceptions.mailbox_errors import MailboxError
from app.domain.ports.mailbox_code_reader import IMailboxConnections
from app.domain.value_objects.mailbox_verification import MailboxMapping


class ManageMailboxConnectionUseCase:
    def __init__(self, connections: IMailboxConnections, sessions: MailboxAttemptSessions):
        self._connections = connections
        self._sessions = sessions

    async def begin_login(self, account_hint=None):
        return await self._connections.begin_login(account_hint)

    async def login_status(self, login_id):
        return await self._connections.login_status(login_id)

    async def cancel_login(self, login_id):
        # Login IDs are connection IDs; a completed login can already own attempts.
        await finish_owned(self._revoke(login_id, self._connections.cancel_login, asyncio.current_task()))

    async def list_connections(self):
        return await self._connections.list_connections()

    async def set_mapping(self, connection_id, mapping: MailboxMapping):
        if self._sessions.is_connection_busy(connection_id):
            raise MailboxError("BUSY")
        await self._connections.set_mapping(connection_id, mapping)
        views = await self._connections.list_connections()
        return next(v for v in views if v.id == connection_id)

    async def disconnect(self, connection_id):
        # Invalidate the admission fence before canceling auth/cache operations.
        await finish_owned(self._revoke(connection_id, self._connections.disconnect, asyncio.current_task()))

    async def _revoke(self, connection_id, revoke, caller):
        await self._sessions.invalidate_connection(connection_id, "DISCONNECTED", caller=caller)
        await revoke(connection_id)
        self._sessions.retire_connection(connection_id)
