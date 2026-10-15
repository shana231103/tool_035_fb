# File: backend/app/infrastructure/mail/microsoft_refresh_token_auth.py
import asyncio
import time

from app.application.mailbox_lifecycle import finish_owned
from app.domain.exceptions.mailbox_errors import MailboxError
from app.domain.ports.mailbox_auth import IMailboxAuth
from app.domain.value_objects.mailbox_credentials import MailboxAuthIdentity, MailboxCredentials
from .oauth_refresh_exchange import AUTHORITY, OAuthRefreshExchange, remaining_budget
from .refresh_auth_state import RefreshAuthState, drain_exchange


class MicrosoftRefreshTokenAuth(IMailboxAuth):
    """Per-connection RAM credentials with one owned, bounded refresh task."""

    def __init__(self, *, authority: str, http_timeout: float = 10, exchange=None,
                 max_exchanges: int = 2, clock=time.monotonic):
        if authority != AUTHORITY:
            raise ValueError("Unsupported Microsoft authority")
        if (not 0 < http_timeout <= 10 or type(max_exchanges) is not int or max_exchanges < 1):
            raise ValueError("Invalid authentication limits")
        self.exchange = exchange or OAuthRefreshExchange(http_timeout=http_timeout, clock=clock)
        self.clock, self.max_exchanges = clock, max_exchanges
        self.states: dict[str, RefreshAuthState] = {}
        self.closed = False

    def _active(self, connection_id):
        state = self.states.get(connection_id)
        if self.closed or state is None:
            raise MailboxError("DISCONNECTED")
        if not state.active:
            raise MailboxError(state.reason or "DISCONNECTED")
        return state

    def assert_active(self, connection_id: str) -> None:
        self._active(connection_id)

    def _has_capacity(self):
        pending = sum(s.exchange_task is not None and not s.exchange_task.done()
                      for s in self.states.values())
        if pending >= self.max_exchanges:
            raise MailboxError("BUSY")

    async def import_credentials(self, connection_id: str, credentials: MailboxCredentials,
                                 deadline: float) -> None:
        if self.closed:
            raise MailboxError("DISCONNECTED")
        remaining_budget(deadline, self.clock)
        if connection_id in self.states:
            raise MailboxError("BUSY")
        self._has_capacity()
        self.states[connection_id] = RefreshAuthState(
            credentials.email, credentials.client_id, credentials.refresh_token)
        try:
            await self.acquire_access_token(connection_id, deadline)
        except BaseException:
            await finish_owned(self.dispose(connection_id))
            raise

    def bind_identity(self, connection_id: str, identity: MailboxAuthIdentity) -> None:
        state = self._active(connection_id)
        if identity.primary_email != state.email:
            raise MailboxError("MAPPING_INVALID")
        state.identity = identity

    def identity(self, connection_id: str) -> MailboxAuthIdentity:
        state = self._active(connection_id)
        if state.identity is None:
            raise MailboxError("AUTH_REQUIRED")
        return state.identity

    async def _refresh(self, connection_id, state, generation, deadline):
        started = self.clock()
        credentials = MailboxCredentials(state.email, state.refresh_token, state.client_id)
        try:
            async with asyncio.timeout(remaining_budget(deadline, self.clock)):
                grant = await self.exchange.exchange(credentials, deadline)
            remaining_budget(deadline, self.clock)
            if (self.states.get(connection_id) is not state or not state.active
                    or generation != state.generation or self.closed):
                raise MailboxError("DISCONNECTED")
            refresh_after = started + grant.expires_in - min(60, grant.expires_in * .1)
            if self.clock() >= refresh_after:
                raise MailboxError("MAILBOX_UNAVAILABLE")
            if grant.refresh_token is not None:
                try:
                    MailboxCredentials(state.email, grant.refresh_token, state.client_id)
                except MailboxError:
                    raise MailboxError("GRAPH_PROTOCOL_ERROR") from None
            state.access_token = grant.access_token
            if grant.refresh_token is not None:
                state.refresh_token = grant.refresh_token
            state.refresh_after = refresh_after
            return state.access_token
        except MailboxError as error:
            if error.reason in {"AUTH_REQUIRED", "CONFIGURATION_REQUIRED", "APP_CONSENT_REQUIRED",
                                "MAIL_READ_REQUIRED", "GRAPH_PROTOCOL_ERROR"} and state.active:
                state.active, state.reason = False, error.reason
                state.generation += 1
                state.clear_secrets()
            raise
        except TimeoutError:
            raise MailboxError("MAILBOX_UNAVAILABLE") from None
        finally:
            if state.exchange_task is asyncio.current_task():
                state.exchange_task = None

    @staticmethod
    def _observe(task):
        if not task.cancelled():
            task.exception()

    async def acquire_access_token(self, connection_id: str, deadline: float, *,
                                   force_refresh: bool = False) -> str:
        state = self._active(connection_id)
        remaining = remaining_budget(deadline, self.clock)
        async with state.lock:
            self._active(connection_id)
            if (not force_refresh and state.access_token and self.clock() < state.refresh_after):
                return state.access_token
            task = state.exchange_task
            if task is None:
                self._has_capacity()
                task = asyncio.create_task(self._refresh(connection_id, state, state.generation,
                    min(deadline, self.clock() + 30)))
                state.exchange_task = task
                task.add_done_callback(self._observe)
        try:
            async with asyncio.timeout(remaining):
                token = await asyncio.shield(task)
        except asyncio.CancelledError:
            if not state.active:
                self._active(connection_id)
            raise
        except TimeoutError:
            raise MailboxError("MAILBOX_UNAVAILABLE") from None
        self._active(connection_id)
        remaining_budget(deadline, self.clock)
        return token

    def revoke(self, connection_id: str) -> None:
        state = self.states.get(connection_id)
        if state is not None:
            state.active, state.reason = False, "DISCONNECTED"
            state.generation += 1
            state.clear_secrets()
            if state.exchange_task is not None:
                state.exchange_task.cancel()

    async def dispose(self, connection_id: str) -> None:
        state = self.states.get(connection_id)
        if state is None:
            return
        self.revoke(connection_id)
        try:
            await finish_owned(drain_exchange(state.exchange_task))
        finally:
            state.clear_secrets()
            state.exchange_task = None
            if self.states.get(connection_id) is state:
                self.states.pop(connection_id)

    async def shutdown(self) -> None:
        self.closed = True
        keys = tuple(self.states)
        for key in keys:
            self.revoke(key)
        try:
            await finish_owned(asyncio.gather(*(self.dispose(key) for key in keys)))
        finally:
            await finish_owned(self.exchange.close())
