# File: backend/app/application/request_authority.py
"""Transaction-local request authority guards and validation."""

from typing import Any
from uuid import UUID
from app.domain.entities.operator_account import OperatorAccountStatus
from app.domain.exceptions.operator_errors import (
    AccountDisabledError,
    OwnedResourceNotFoundError,
    SessionExpiredError,
    SessionRevokedError,
)
from app.domain.ports.operator_security import IClock
from app.domain.value_objects.operator_identity import AccountMetadata, OperatorPrincipal


class RequestAuthorityGuard:
    """Enforces atomic request authority checks inside the same write transaction."""

    def __init__(self, clock: IClock):
        self._clock = clock

    async def validate_request_write(self, uow: Any, principal: OperatorPrincipal) -> AccountMetadata:
        now = self._clock.now()
        if now >= principal.absolute_expires_at:
            raise SessionExpiredError("Session absolute timeout expired")
        if now >= principal.idle_expires_at:
            raise SessionExpiredError("Session idle timeout expired")

        if uow.accounts is None or uow.sessions is None:
            raise RuntimeError("Request authority repositories are not configured.")
        account = await uow.accounts.get(principal.operator_id)
        if not account or account.status != OperatorAccountStatus.ACTIVE:
            raise AccountDisabledError("Operator account is not active")
        session = await uow.sessions.get_by_id(principal.session_id)
        if (session is None or session.operator_id != principal.operator_id
                or session.revoked_at is not None or session.auth_version != principal.auth_version
                or account.auth_version != principal.auth_version):
            raise SessionRevokedError("Session authority is no longer valid")
        if now >= session.expires_at or now >= session.idle_expires_at:
            raise SessionExpiredError("Persisted session timeout expired")
        return AccountMetadata(account.id, account.username_display, account.status,
                               account.auth_version, account.run_version,
                               account.created_at, account.updated_at)

    def assert_resource_owned(self, principal: OperatorPrincipal, resource: Any) -> None:
        if resource is None:
            raise OwnedResourceNotFoundError("Resource not found")
        owner = getattr(resource, "operator_account_id", None) or getattr(resource, "operator_id", None)
        if owner != principal.operator_id:
            raise OwnedResourceNotFoundError("Resource does not belong to principal")
