# File: backend/app/infrastructure/mail/microsoft_auth.py
import asyncio
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit
from uuid import UUID

import msal

from app.domain.exceptions.mailbox_errors import MailboxError
from app.domain.value_objects.mailbox_verification import DeviceLoginPrompt
from .auth_state import AuthState, join_worker

SCOPES = ["https://graph.microsoft.com/User.Read", "https://graph.microsoft.com/Mail.Read"]


class MicrosoftAuth:
    """One in-memory MSAL cache and serialized SDK calls per connection."""

    def __init__(self, client_id: str, authority: str, http_timeout: float = 10, *,
                 app_factory=None, max_workers: int = 2, on_cache_changed=None):
        parsed = urlsplit(authority)
        if (parsed.scheme != "https" or parsed.hostname != "login.microsoftonline.com"
                or parsed.username or parsed.port not in (None, 443) or parsed.query or parsed.fragment):
            raise ValueError("Unsupported Microsoft authority")
        if not 0 < http_timeout <= 10 or max_workers < 1:
            raise ValueError("Invalid authentication limits")
        self.client_id, self.authority, self.http_timeout = client_id, authority, http_timeout
        self.factory = app_factory or msal.PublicClientApplication
        self.max_workers, self.states, self.closed = max_workers, {}, False
        self.on_cache_changed = on_cache_changed

    def configure_client_id(self, client_id: str) -> None:
        """Change the public application ID only when no auth work/session owns it."""
        try:
            normalized = str(UUID(client_id))
        except (ValueError, TypeError, AttributeError):
            raise MailboxError("CONFIGURATION_REQUIRED") from None
        if self.closed:
            raise MailboxError("DISCONNECTED")
        if normalized == self.client_id:
            return
        if self.states:
            raise MailboxError("BUSY")
        self.client_id = normalized

    def restore_state(self, connection_id: str, account: dict, serialized_cache: str) -> None:
        if self.closed:
            raise MailboxError("DISCONNECTED")
        cache = msal.SerializableTokenCache()
        if serialized_cache:
            try:
                cache.deserialize(serialized_cache)
            except Exception:
                pass
        state = AuthState(cache)
        state.account = account
        state.app = self.factory(self.client_id, authority=self.authority, token_cache=state.cache,
                                 timeout=self.http_timeout, enable_pii_log=False)
        self.states[connection_id] = state

    def export_cache(self, connection_id: str) -> str | None:
        state = self.states.get(connection_id)
        if state and hasattr(state.cache, "serialize"):
            return state.cache.serialize()
        return None

    async def begin_device_login(self, connection_id: str) -> DeviceLoginPrompt:
        if not self.client_id:
            raise MailboxError("CONFIGURATION_REQUIRED")
        if self.closed or len(self.states) >= self.max_workers:
            pending = sum(s.worker is not None and not s.worker.done() for s in self.states.values())
            if self.closed or pending >= self.max_workers:
                raise MailboxError("BUSY")
        if connection_id in self.states:
            raise MailboxError("BUSY")
        state = AuthState(msal.SerializableTokenCache())
        self.states[connection_id] = state
        state.worker = asyncio.create_task(asyncio.to_thread(self._initiate, state))
        try:
            flow = await asyncio.shield(state.worker)
            if not state.active or not flow.get("user_code"):
                raise MailboxError("AUTH_REQUIRED")
            uri = urlsplit(flow.get("verification_uri", ""))
            if (uri.scheme != "https" or uri.hostname not in
                    {"microsoft.com", "www.microsoft.com", "login.microsoftonline.com", "login.microsoft.com"}
                    or uri.username or uri.password or uri.port not in (None, 443)
                    or (uri.hostname == "login.microsoft.com" and
                        (uri.path != "/device" or uri.query or uri.fragment))):
                raise MailboxError("GRAPH_PROTOCOL_ERROR")
            prompt = DeviceLoginPrompt(connection_id, flow["verification_uri"], flow["user_code"],
                                       datetime.fromtimestamp(flow["expires_at"], timezone.utc),
                                       int(flow.get("interval", 5)))
            state.worker = asyncio.create_task(self._poll(state))
            return prompt
        except (asyncio.CancelledError, MailboxError):
            await self.cancel_login(connection_id)
            raise
        except Exception:
            await self.cancel_login(connection_id)
            raise MailboxError("AUTH_REQUIRED") from None

    def _initiate(self, state):
        state.app = self.factory(self.client_id, authority=self.authority, token_cache=state.cache,
                                 timeout=self.http_timeout, enable_pii_log=False)
        state.flow = state.app.initiate_device_flow(scopes=SCOPES)
        if not state.active:
            state.flow["expires_at"] = 0
        return state.flow

    async def _poll(self, state):
        try:
            async with state.lock:
                result = await asyncio.to_thread(state.app.acquire_token_by_device_flow, state.flow)
                accounts = state.app.get_accounts() if state.active else []
                if state.active and result.get("access_token") and not self._has_mail_read(result):
                    state.reason = "MAIL_READ_REQUIRED"
                elif state.active and result.get("access_token") and len(accounts) == 1:
                    state.account = accounts[0]
                elif state.active:
                    state.reason = ("LOGIN_EXPIRED" if state.flow.get("expires_at", 0) <= time.time() else
                                    "APP_CONSENT_REQUIRED" if result.get("error") == "consent_required" else "AUTH_REQUIRED")
        except Exception:
            state.reason = "AUTH_REQUIRED"
        finally:
            if not state.active:
                self._clear(state)

    def identity(self, connection_id: str) -> dict:
        state = self.states.get(connection_id)
        if not state or not state.active or not state.account:
            raise MailboxError(state.reason if state and state.reason else "AUTH_REQUIRED")
        return dict(state.account)

    def login_complete(self, connection_id: str) -> bool:
        state = self.states.get(connection_id)
        return bool(state and state.worker and state.worker.done())

    async def acquire_access_token(self, connection_id: str, deadline: float, *, force_refresh: bool = False) -> str:
        state = self.states.get(connection_id)
        if not state or not state.active or not state.account or deadline <= time.monotonic():
            raise MailboxError("AUTH_REQUIRED")
        async with state.lock:
            if not state.active or deadline <= time.monotonic():
                raise MailboxError("AUTH_REQUIRED")
            worker = asyncio.create_task(asyncio.to_thread(
                state.app.acquire_token_silent, SCOPES, account=state.account, force_refresh=force_refresh))
            state.worker = worker
            try:
                result = await asyncio.shield(worker)
            except asyncio.CancelledError:
                await join_worker(worker)
                raise
            except Exception:
                raise MailboxError("AUTH_REQUIRED") from None
            if not state.active or time.monotonic() >= deadline or not result or not result.get("access_token"):
                raise MailboxError("AUTH_REQUIRED")
            if not self._has_mail_read(result) and (force_refresh or not self._has_cached_scopes(state, result)):
                raise MailboxError("CONSENT_REQUIRED")
            if getattr(state.cache, "has_state_changed", False):
                state.cache.has_state_changed = False
                if self.on_cache_changed:
                    try:
                        self.on_cache_changed(connection_id, state.cache.serialize())
                    except Exception:
                        pass
            return result["access_token"]

    def _has_cached_scopes(self, state, result):
        # MSAL cache-hit responses omit scope; verify the exact cached credential.
        if "scope" in result or result.get("token_source") != "cache":
            return False
        account = state.account
        if not all(account.get(key) for key in ("home_account_id", "environment", "realm")):
            return False
        environment = account["environment"]
        if environment.casefold() != urlsplit(self.authority).hostname:
            return False
        query = {"client_id": self.client_id, "home_account_id": account["home_account_id"],
                 "environment": environment, "realm": account["realm"], "secret": result["access_token"]}
        now = time.time()  # The search fast path can yield an expired exact-key entry.
        return any(int(entry.get("expires_on", 0)) > now for entry in
                   state.cache.search(msal.TokenCache.CredentialType.ACCESS_TOKEN, target=SCOPES, query=query))

    @staticmethod
    def _has_mail_read(result):
        return "mail.read" in {scope.casefold().removeprefix("https://graph.microsoft.com/")
                                for scope in result.get("scope", "").split()}

    async def cancel_login(self, login_id: str) -> None:
        state = self.states.get(login_id)
        if state is None:
            return
        state.active = False
        state.flow["expires_at"] = 0
        try:
            if state.worker is not None:
                await join_worker(state.worker)
        finally:
            self._clear(state)
            self.states.pop(login_id, None)

    @staticmethod
    def _clear(state):
        try:
            if state.app is not None:
                for account in state.app.get_accounts():
                    state.app.remove_account(account)
        finally:
            state.account = None
            state.flow.clear()
            state.app = None
            state.cache = msal.SerializableTokenCache()

    async def shutdown(self) -> None:
        self.closed = True
        results = await asyncio.gather(*(self.cancel_login(key) for key in tuple(self.states)),
                                       return_exceptions=True)
        if any(isinstance(result, BaseException) for result in results):
            raise MailboxError("AUTH_REQUIRED")
