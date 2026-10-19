# File: backend/app/presentation/api/operator_auth.py
"""FastAPI dependencies for operator session authentication and CSRF guards."""

from typing import AsyncGenerator
from fastapi import Depends, HTTPException, Request, status
from app.application.unit_of_work import IUnitOfWork
from app.domain.exceptions.operator_errors import (
    AuthenticationRequiredError,
    CsrfInvalidError,
    SessionExpiredError,
    SessionRevokedError,
)
from app.domain.value_objects.operator_identity import OperatorPrincipal
from app.presentation.api.operator_composition import (
    get_auth_service,
    get_ingress_policy,
    get_scoped_uow_factory,
    get_session_secrets,
)


async def get_current_principal(request: Request) -> OperatorPrincipal:
    policy = get_ingress_policy()
    auth_service = get_auth_service()
    cookie = request.cookies.get(policy.cookie_name)

    if not cookie:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    try:
        # Touch session during authenticated request
        return await auth_service.authenticate(cookie, touch=True)
    except (AuthenticationRequiredError, SessionExpiredError, SessionRevokedError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.message,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
        )


def require_csrf(
    request: Request,
    principal: OperatorPrincipal = Depends(get_current_principal),
) -> None:
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        policy = get_ingress_policy()
        secrets = get_session_secrets()
        cookie = request.cookies.get(policy.cookie_name)
        token = request.headers.get("X-CSRF-Token")

        if not cookie or not token or not secrets.verify_csrf(cookie, token):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid or missing CSRF token",
            )


def require_session_context(
    request: Request,
    principal: OperatorPrincipal = Depends(get_current_principal),
) -> None:
    context_hdr = request.headers.get("X-Operator-Session")
    if context_hdr and context_hdr != str(principal.session_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session context mismatch",
        )


async def get_scoped_uow(
    principal: OperatorPrincipal = Depends(get_current_principal),
) -> AsyncGenerator[IUnitOfWork, None]:
    factory = get_scoped_uow_factory()
    async with factory.operator(principal.operator_id) as uow:
        yield uow
