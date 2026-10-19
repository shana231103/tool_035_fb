# File: backend/app/application/operator_accounts.py
"""Application service for operator account creation, credential reset, and status control."""

from typing import Callable, List
from uuid import UUID, uuid4

from app.application.operator_records import AccountMetadata
from app.application.unit_of_work import IAuthUnitOfWork
from app.domain.entities.operator_account import OperatorAccount
from app.domain.exceptions.operator_errors import OperatorError
from app.domain.ports.operator_security import IClock, IPasswordHasher
from app.domain.value_objects.operator_identity import OperatorAccountStatus


class OperatorAccountService:
    """Manages operator accounts with password hashing outside transactions."""

    def __init__(
        self,
        auth_factory: Callable[[], IAuthUnitOfWork],
        hasher: IPasswordHasher,
        clock: IClock,
    ):
        self._auth_factory = auth_factory
        self._hasher = hasher
        self._clock = clock

    def _uow(self, write: bool = False):
        if hasattr(self._auth_factory, "auth"):
            return self._auth_factory.auth(write=write)
        try:
            return self._auth_factory(write=write)
        except TypeError:
            return self._auth_factory()

    async def create(self, username: str, password: str) -> AccountMetadata:
        key, display = OperatorAccount.normalize_username(username)
        OperatorAccount.validate_password_bounds(password)
        encoded_hash = await self._hasher.hash(password)
        now = self._clock.now()

        async with self._uow(write=True) as uow:
            existing = await uow.accounts.find_login(key)
            if existing:
                raise OperatorError(f"Username '{display}' already exists")

            account = OperatorAccount(
                id=uuid4(),
                username_key=key,
                username_display=display,
                password_hash=encoded_hash,
                status=OperatorAccountStatus.ACTIVE,
                auth_version=1,
                run_version=1,
                created_at=now,
                updated_at=now,
            )
            await uow.accounts.insert(account)
            await uow.commit()

        return AccountMetadata(
            id=account.id,
            username_display=display,
            status=account.status,
            auth_version=account.auth_version,
            run_version=account.run_version,
            created_at=account.created_at,
            updated_at=account.updated_at,
        )

    async def reset_password(self, id: UUID, password: str) -> None:
        OperatorAccount.validate_password_bounds(password)
        encoded_hash = await self._hasher.hash(password)
        now = self._clock.now()

        async with self._uow(write=True) as uow:
            acc = await uow.accounts.get(id)
            if not acc or acc.is_quarantined:
                raise OperatorError(f"Account {id} not found")

            await uow.accounts.change_credentials(id, acc.auth_version, encoded_hash)
            await uow.sessions.revoke_account(id, now)
            await uow.commit()

    async def disable(self, id: UUID) -> None:
        now = self._clock.now()
        async with self._uow(write=True) as uow:
            acc = await uow.accounts.get(id)
            if not acc or acc.is_quarantined:
                raise OperatorError(f"Account {id} not found")
            await uow.accounts.set_enabled(id, enabled=False)
            await uow.sessions.revoke_account(id, now)
            await uow.commit()

    async def enable(self, id: UUID) -> None:
        async with self._uow(write=True) as uow:
            acc = await uow.accounts.get(id)
            if not acc or acc.is_quarantined:
                raise OperatorError(f"Account {id} not found")
            await uow.accounts.set_enabled(id, enabled=True)
            await uow.commit()

    async def revoke_sessions(self, id: UUID) -> None:
        now = self._clock.now()
        async with self._uow(write=True) as uow:
            acc = await uow.accounts.get(id)
            if not acc:
                raise OperatorError(f"Account {id} not found")
            await uow.accounts.bump_auth_version(id)
            await uow.sessions.revoke_account(id, now)
            await uow.commit()

    async def list_accounts(self, limit: int = 50, offset: int = 0) -> List[AccountMetadata]:
        async with self._uow(write=False) as uow:
            return await uow.accounts.list_metadata(limit, offset)
