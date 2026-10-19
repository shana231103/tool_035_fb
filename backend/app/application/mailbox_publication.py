# File: backend/app/application/mailbox_publication.py
"""Staged mailbox publication gate."""

import asyncio
from typing import Awaitable, Callable, Optional
from uuid import UUID

from app.domain.exceptions.mailbox_errors import MailboxError
from app.domain.value_objects.operator_identity import OperatorPrincipal
from .mailbox_lifecycle import MailboxLocks, finish_owned


async def publish_if_session_current(
    principal: OperatorPrincipal,
    reservation_id: str,
    stage: Callable[[], None],
    activate: Callable[[], None],
    retire: Callable[[], Awaitable[None]],
    session_authorizer: Optional[Callable[[UUID, UUID], Awaitable[bool]]] = None,
    locks: Optional[MailboxLocks] = None,
) -> None:
    """Publication gate for mailbox connection publication:
    - Verifies initiating session and account are valid before publishing (revoke-first cannot publish).
    - Under visibility and connection locks, stages candidate invisible as ADMISSION_PENDING.
    - Re-verifies session validity under lock before committing.
    - Synchronously activates connection before visibility release.
    - On any rollback, failure, or unknown commit, drains and retires candidate outside DB.
    """
    if session_authorizer is not None:
        valid = await session_authorizer(principal.operator_id, principal.session_id)
        if not valid:
            await finish_owned(retire())
            raise MailboxError("DISCONNECTED")

    lock_context = locks.hold(reservation_id) if locks is not None else asyncio.Lock()

    async with lock_context:
        if session_authorizer is not None:
            valid = await session_authorizer(principal.operator_id, principal.session_id)
            if not valid:
                await finish_owned(retire())
                raise MailboxError("DISCONNECTED")

        try:
            stage()
        except Exception:
            await finish_owned(retire())
            raise

        if session_authorizer is not None:
            valid = await session_authorizer(principal.operator_id, principal.session_id)
            if not valid:
                await finish_owned(retire())
                raise MailboxError("DISCONNECTED")

        try:
            activate()
        except Exception:
            await finish_owned(retire())
            raise
