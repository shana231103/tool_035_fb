# File: backend/app/presentation/api/operator_composition.py
"""Composition root wiring auth services, security ports, and scoped factories."""

from datetime import datetime, timezone
import time
from typing import Optional

from app.application.operator_accounts import OperatorAccountService
from app.application.operator_auth import OperatorAuthService
from app.core.config import settings
from app.domain.ports.operator_security import IClock
from app.infrastructure.auth.login_limits import InMemoryLoginLimits
from app.infrastructure.auth.passwords import Argon2PasswordHasher
from app.infrastructure.auth.session_secrets import SessionSecrets
from app.infrastructure.persistence.database import db_manager
from app.infrastructure.persistence.operator_uow import AuthUnitOfWorkFactory
from app.infrastructure.persistence.sql_unit_of_work import (
    ScopedUnitOfWorkFactory,
    SystemUnitOfWorkFactory,
)
from app.presentation.api.hosted_policy import IngressPolicy


class PresentationSystemClock(IClock):
    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def monotonic(self) -> float:
        return time.monotonic()


_ingress_policy = IngressPolicy(
    mode=getattr(settings, "operator_deployment_mode", "local"),
    public_origin=getattr(settings, "operator_public_origin", None),
)
_secrets = SessionSecrets()
_hasher = Argon2PasswordHasher()
_limits = InMemoryLoginLimits()
_clock = PresentationSystemClock()

_auth_uow_factory: Optional[AuthUnitOfWorkFactory] = None
_scoped_uow_factory: Optional[ScopedUnitOfWorkFactory] = None
_system_uow_factory: Optional[SystemUnitOfWorkFactory] = None

_auth_service: Optional[OperatorAuthService] = None
_account_service: Optional[OperatorAccountService] = None


def get_ingress_policy() -> IngressPolicy:
    return _ingress_policy


def set_ingress_policy(policy: IngressPolicy) -> None:
    global _ingress_policy
    _ingress_policy = policy


def get_session_secrets() -> SessionSecrets:
    return _secrets


def get_scoped_uow_factory() -> ScopedUnitOfWorkFactory:
    global _scoped_uow_factory
    if _scoped_uow_factory is None:
        _scoped_uow_factory = ScopedUnitOfWorkFactory(db_manager)
    return _scoped_uow_factory


def get_auth_service() -> OperatorAuthService:
    global _auth_service, _auth_uow_factory
    if _auth_service is None:
        if _auth_uow_factory is None:
            _auth_uow_factory = AuthUnitOfWorkFactory(db_manager._sessionmaker)
        _auth_service = OperatorAuthService(
            _auth_uow_factory, _hasher, _secrets, _limits, _clock
        )
    return _auth_service


def get_account_service() -> OperatorAccountService:
    global _account_service, _auth_uow_factory
    if _account_service is None:
        if _auth_uow_factory is None:
            _auth_uow_factory = AuthUnitOfWorkFactory(db_manager._sessionmaker)
        _account_service = OperatorAccountService(
            _auth_uow_factory, _hasher, _clock
        )
    return _account_service


def reset_composition() -> None:
    global _auth_service, _account_service, _auth_uow_factory, _scoped_uow_factory, _system_uow_factory, _ingress_policy
    _auth_service = None
    _account_service = None
    _auth_uow_factory = None
    _scoped_uow_factory = None
    _system_uow_factory = None
    _ingress_policy = IngressPolicy(
        mode=getattr(settings, "operator_deployment_mode", "local"),
        public_origin=getattr(settings, "operator_public_origin", None),
    )
