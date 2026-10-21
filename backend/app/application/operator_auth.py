# File: backend/app/application/operator_auth.py
"""Operator authentication service handling login issuance, validation, and logout."""

from datetime import timedelta
from typing import Callable, Optional
from uuid import uuid4

from app.application.operator_records import LoginCommand, SessionGrant, SessionView
from app.application.operator_session_validation import OperatorSessionValidator
from app.application.unit_of_work import IAuthUnitOfWork
from app.domain.exceptions.operator_errors import (
    AuthenticationRequiredError,
    CsrfInvalidError,
    InvalidCredentialsError,
    StaleLoginProofError,
)
from app.domain.ports.operator_security import (
    IClock,
    ILoginLimits,
    IPasswordHasher,
    ISessionSecrets,
)
from app.domain.value_objects.operator_identity import (
    OperatorPrincipal,
    SessionRecord,
)

DUMMY_HASH = "$argon2id$v=19$m=19456,t=2,p=1$c29tZXNhbHQ$9Z6c1x5x1x5x1x5x1x5x1x5x1x5x1x5x1x5x1x5x1x4"


class OperatorAuthService:
    """Orchestrates secure authentication, session creation, and revalidation."""

    def __init__(
        self,
        auth_factory: Callable[[], IAuthUnitOfWork],
        hasher: IPasswordHasher,
        secrets: ISessionSecrets,
        limits: ILoginLimits,
        clock: IClock,
    ):
        self._auth_factory = auth_factory
        self._hasher = hasher
        self._secrets = secrets
        self._limits = limits
        self._clock = clock

    def _uow(self, write: bool = False):
        if hasattr(self._auth_factory, "auth"):
            return self._auth_factory.auth(write=write)
        try:
            return self._auth_factory(write=write)
        except TypeError:
            return self._auth_factory()

    async def login(
        self,
        command: LoginCommand,
        previous_cookie: Optional[str] = None,
        client_ip: str = "127.0.0.1",
    ) -> SessionGrant:
        username_key = command.username.strip().casefold()
        await self._limits.acquire(username_key, client_ip)

        now = self._clock.now()
        async with self._uow(write=False) as uow:
            account = await uow.accounts.find_login(username_key)

        if not account or not account.is_active or not account.password_hash:
            await self._hasher.verify(DUMMY_HASH, command.password)
            self._limits.record_failure(username_key, client_ip)
            raise InvalidCredentialsError()

        valid = await self._hasher.verify(account.password_hash, command.password)
        if not valid:
            self._limits.record_failure(username_key, client_ip)
            raise InvalidCredentialsError()

        secret = self._secrets.new_secret()
        digest = self._secrets.digest(secret)
        csrf_token = self._secrets.csrf(secret)
        abs_exp = now + timedelta(hours=12)
        idle_exp = now + timedelta(minutes=30)
        session_id = uuid4()

        async with self._uow(write=True) as uow:
            current = await uow.accounts.lock(account.id)
            if not current.is_active or current.auth_version != account.auth_version:
                raise StaleLoginProofError("Credentials changed during login. Please retry.")

            if previous_cookie:
                prev_digest = self._secrets.digest(previous_cookie)
                prev_rec = await uow.sessions.get_by_digest(prev_digest)
                if prev_rec and prev_rec.revoked_at is None:
                    await uow.sessions.revoke(prev_rec.id, now)

            rec = SessionRecord(
                id=session_id,
                secret_digest=digest,
                operator_id=current.id,
                auth_version=current.auth_version,
                created_at=now,
                last_seen_at=now,
                expires_at=abs_exp,
                idle_expires_at=idle_exp,
            )
            await uow.sessions.insert(rec)
            await uow.commit()

        self._limits.record_success(username_key, client_ip)

        view = SessionView(
            authenticated=True,
            operator={"id": str(current.id), "username": current.username_display or current.username_key or ""},
            session_context=session_id,
            csrf_token=csrf_token,
            expires_at=abs_exp,
            idle_expires_at=idle_exp,
        )
        return SessionGrant(view=view, cookie_secret=secret)

    async def authenticate(self, cookie: str, touch: bool = False) -> OperatorPrincipal:
        if not cookie:
            raise AuthenticationRequiredError()

        digest = self._secrets.digest(cookie)
        return await OperatorSessionValidator(self._uow, self._clock).authenticate(
            digest, touch=touch,
        )

    async def session(self, cookie: Optional[str]) -> SessionView:
        if not cookie:
            return SessionView.anonymous()
        try:
            principal = await self.authenticate(cookie, touch=False)
            async with self._uow(write=False) as uow:
                acc = await uow.accounts.get(principal.operator_id)
            username = acc.username_display if acc else ""
            csrf_token = self._secrets.csrf(cookie)
            return SessionView(
                authenticated=True,
                operator={"id": str(principal.operator_id), "username": username or ""},
                session_context=principal.session_id,
                csrf_token=csrf_token,
                expires_at=principal.absolute_expires_at,
                idle_expires_at=principal.idle_expires_at,
            )
        except Exception:
            return SessionView.anonymous()

    async def logout(self, principal: OperatorPrincipal, csrf: str, cookie: str) -> None:
        if not self._secrets.verify_csrf(cookie, csrf):
            raise CsrfInvalidError()

        now = self._clock.now()
        async with self._uow(write=True) as uow:
            await uow.sessions.revoke(principal.session_id, now)
            await uow.commit()
