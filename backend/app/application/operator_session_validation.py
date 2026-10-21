# File: backend/app/application/operator_session_validation.py
"""Persisted session validation with a bounded activity persistence window."""

from datetime import timedelta
from typing import Callable

from app.application.unit_of_work import IAuthUnitOfWork
from app.domain.exceptions.operator_errors import (
    AuthenticationRequiredError, SessionExpiredError, SessionRevokedError,
)
from app.domain.ports.operator_security import IClock
from app.domain.value_objects.operator_identity import OperatorPrincipal, SessionRecord

TOUCH_INTERVAL = timedelta(seconds=30)


class OperatorSessionValidator:
    """Validate each request; persist activity at most once per 30-second window.

    Nominal idle lifetime remains 30 minutes, with its persisted deadline up to
    30 seconds earlier than recording every request; absolute expiry stays fixed.
    """

    def __init__(self, uow_factory: Callable[..., IAuthUnitOfWork], clock: IClock):
        self._uow = uow_factory
        self._clock = clock

    async def authenticate(self, digest: bytes, *, touch: bool) -> OperatorPrincipal:
        async with self._uow(write=False) as uow:
            record, now = await self._load(uow, digest)
            due = touch and now - record.last_seen_at >= TOUCH_INTERVAL
        if not due:
            return self._principal(record)

        # __aenter__ acquires writer admission before either the read or clock.
        async with self._uow(write=True) as uow:
            record, now = await self._load(uow, digest)
            if now - record.last_seen_at < TOUCH_INTERVAL:
                return self._principal(record)
            changed = await uow.sessions.touch(
                record.id, record.auth_version, now, min_interval=TOUCH_INTERVAL,
            )
            if not changed:
                # Never grant authorization using the pre-update record.
                raise AuthenticationRequiredError()
            record, _ = await self._load(uow, digest)
            await uow.commit()
        return self._principal(record)

    async def _load(self, uow: IAuthUnitOfWork, digest: bytes):
        record = await uow.sessions.get_by_digest(digest)
        if record is None:
            raise AuthenticationRequiredError()
        account = await uow.accounts.get(record.operator_id)
        now = self._clock.now()
        if record.revoked_at is not None:
            raise SessionRevokedError()
        if now >= record.expires_at or now >= record.idle_expires_at:
            raise SessionExpiredError()
        if not account or not account.is_active or account.auth_version != record.auth_version:
            raise SessionRevokedError("Account disabled or credentials changed")
        return record, now

    @staticmethod
    def _principal(record: SessionRecord) -> OperatorPrincipal:
        return OperatorPrincipal(
            operator_id=record.operator_id,
            session_id=record.id,
            auth_version=record.auth_version,
            absolute_expires_at=record.expires_at,
            idle_expires_at=record.idle_expires_at,
        )
