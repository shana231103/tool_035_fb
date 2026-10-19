# File: backend/app/presentation/ws/session_channels.py
"""Authorizer and idle sweeper for WebSocket session channels."""

import asyncio
from datetime import datetime
import logging
from typing import Any, Optional
from uuid import UUID

from app.application.operator_auth import OperatorAuthService
from app.application.unit_of_work import IAuthUnitOfWork
from app.domain.ports.operator_security import IClock
from app.domain.value_objects.operator_identity import (
    OperatorAccountStatus,
    OperatorPrincipal,
    SessionStatus,
)

logger = logging.getLogger(__name__)


class SessionChannelAuthorizer:
    """Authorizes WebSocket send operations and sweeps idle channels."""

    def __init__(
        self,
        auth_service: OperatorAuthService,
        auth_factory: Any,
        clock: IClock,
        manager: Optional[Any] = None,
        sweep_interval: float = 1.0,
        query_timeout: float = 1.0,
    ):
        self._auth_service = auth_service
        self._auth_factory = auth_factory
        self._clock = clock
        self._manager = manager
        self._sweep_interval = sweep_interval
        self._query_timeout = query_timeout
        self._sweeper_task: Optional[asyncio.Task] = None
        self._stopped = False

    def bind_manager(self, manager: Any) -> None:
        self._manager = manager

    async def authorize(
        self, principal: OperatorPrincipal, now: Optional[datetime] = None
    ) -> SessionStatus:
        if now is None:
            now = self._clock.now()
        if now > principal.absolute_expires_at or now > principal.idle_expires_at:
            return SessionStatus.EXPIRED

        try:
            async with asyncio.timeout(self._query_timeout):
                async with self._auth_factory() as uow:
                    statuses = await uow.sessions.list_valid((principal.session_id,), now)
                    status = statuses.get(principal.session_id, SessionStatus.UNKNOWN)
                    if status != SessionStatus.VALID:
                        return status
                    account = await uow.accounts.get(principal.operator_id)
                    if (
                        not account
                        or account.status != OperatorAccountStatus.ACTIVE
                        or account.auth_version != principal.auth_version
                    ):
                        return SessionStatus.REVOKED
                    return SessionStatus.VALID
        except (TimeoutError, Exception) as exc:
            logger.warning("Session channel authorization DB error: %s", exc)
            return SessionStatus.UNKNOWN

    async def sweep_idle(self) -> None:
        if self._manager is None:
            return
        active_items = self._manager.get_active_principals()
        if not active_items:
            return

        now = self._clock.now()
        batch = active_items[:32]
        session_map = {
            principal.session_id: (ws, principal)
            for ws, principal in batch
            if principal is not None
        }
        if not session_map:
            return

        try:
            async with asyncio.timeout(self._query_timeout):
                async with self._auth_factory() as uow:
                    statuses = await uow.sessions.list_valid(
                        tuple(session_map.keys()), now
                    )
                    operator_ids = {p.operator_id for _, p in session_map.values()}
                    accounts = {}
                    for oid in operator_ids:
                        acc = await uow.accounts.get(oid)
                        if acc:
                            accounts[oid] = acc

                    for sess_id, (ws, principal) in session_map.items():
                        status = statuses.get(sess_id, SessionStatus.UNKNOWN)
                        acc = accounts.get(principal.operator_id)
                        if (
                            status in (SessionStatus.REVOKED, SessionStatus.EXPIRED)
                            or not acc
                            or acc.status != OperatorAccountStatus.ACTIVE
                            or acc.auth_version != principal.auth_version
                        ):
                            self._manager.retire_with_code(ws, 4401)
                        elif status != SessionStatus.VALID:
                            self._manager.retire_with_code(ws, 1013)
        except (TimeoutError, Exception) as exc:
            logger.warning("Session channel idle sweep DB error: %s", exc)
            for ws, _ in session_map.values():
                self._manager.retire_with_code(ws, 1013)

    def start_sweeper(self) -> None:
        if self._sweeper_task is None or self._sweeper_task.done():
            self._stopped = False
            self._sweeper_task = asyncio.create_task(self._run_sweeper())

    async def _run_sweeper(self) -> None:
        while not self._stopped:
            try:
                await asyncio.sleep(self._sweep_interval)
                if not self._stopped:
                    await self.sweep_idle()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Error in session channel sweeper: %s", exc)

    async def shutdown(self) -> None:
        self._stopped = True
        if self._sweeper_task and not self._sweeper_task.done():
            self._sweeper_task.cancel()
            try:
                await self._sweeper_task
            except asyncio.CancelledError:
                pass
