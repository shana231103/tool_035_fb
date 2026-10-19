# File: backend/app/application/use_cases/manage_mailbox_connection.py
import asyncio
from app.application.mailbox_sessions import MailboxAttemptSessions
from app.application.mailbox_lifecycle import finish_owned
from app.domain.exceptions.mailbox_errors import MailboxError
from app.domain.ports.mailbox_code_reader import IMailboxConnections
from app.domain.value_objects.mailbox_verification import MailboxMapping


class ManageMailboxConnectionUseCase:
    def __init__(self, connections: IMailboxConnections, sessions: MailboxAttemptSessions,
                 *, owner=None, session_id=None):
        self._connections = connections
        self._sessions = sessions
        self._owner, self._session_id = owner, session_id

    async def reserve_connection(self):
        return await self._connections.reserve_connection(owner=self._owner, session_id=self._session_id)

    async def connect(self, connection_id, credentials):
        return await self._connections.connect(connection_id, credentials,
            owner=self._owner, session_id=self._session_id)

    async def list_connections(self):
        return await self._connections.list_connections(owner=self._owner)

    async def _require_owned(self, connection_id):
        if self._owner is not None:
            views = await self._connections.list_connections(owner=self._owner)
            if not any(view.id == connection_id for view in views):
                raise MailboxError("DISCONNECTED")

    async def set_mapping(self, connection_id, mapping: MailboxMapping):
        await self._require_owned(connection_id)
        if self._sessions.is_connection_busy(connection_id):
            raise MailboxError("BUSY")
        await self._connections.set_mapping(connection_id, mapping, owner=self._owner)
        views = await self._connections.list_connections(owner=self._owner)
        return next(v for v in views if v.id == connection_id)

    async def disconnect(self, connection_id):
        await self._require_owned(connection_id)
        # Invalidate the admission fence before canceling auth/cache operations.
        self._connections.revoke(connection_id, owner=self._owner)
        await finish_owned(self._revoke(connection_id, self._connections.disconnect, asyncio.current_task()))

    async def _revoke(self, connection_id, revoke, caller):
        await self._sessions.invalidate_connection(connection_id, "DISCONNECTED", caller=caller)
        await self._sessions.wait_drained(connection_id)
        await revoke(connection_id, owner=self._owner)
        self._sessions.retire_connection(connection_id)
