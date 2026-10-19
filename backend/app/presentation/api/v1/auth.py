# File: backend/app/presentation/api/v1/auth.py
"""Authentication endpoints for operator login, session validation, and logout."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.application.operator_records import LoginCommand
from app.domain.exceptions.operator_errors import (
    InvalidCredentialsError,
    LoginRateLimitError,
    OperatorError,
)
from app.presentation.api.operator_auth import (
    get_current_principal,
    require_csrf,
    require_session_context,
)
from app.presentation.api.operator_composition import (
    get_auth_service,
    get_ingress_policy,
)
from app.presentation.auth_dtos import LoginRequest, SessionResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=SessionResponse)
async def login(req: LoginRequest, request: Request, response: Response):
    policy = get_ingress_policy()
    auth_service = get_auth_service()

    origin = request.headers.get("origin")
    custom_header = request.headers.get("x-operator-login")
    try:
        policy.check_login_headers(origin, custom_header)
    except OperatorError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=e.message)

    previous_cookie = request.cookies.get(policy.cookie_name)
    client_ip = request.client.host if request.client else "127.0.0.1"

    try:
        grant = await auth_service.login(
            LoginCommand(req.username, req.password),
            previous_cookie=previous_cookie,
            client_ip=client_ip,
        )
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    except LoginRateLimitError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=e.message,
            headers={"Retry-After": str(e.retry_after)},
        )
    except OperatorError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)

    response.set_cookie(
        key=policy.cookie_name,
        value=grant.cookie_secret,
        httponly=True,
        secure=policy.is_cookie_secure,
        samesite="lax",
        path="/",
        max_age=43200,
    )
    return SessionResponse.from_domain(grant.view)


@router.get("/session", response_model=SessionResponse)
async def session(request: Request, response: Response):
    policy = get_ingress_policy()
    auth_service = get_auth_service()

    # Prevent caching of session status
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    cookie = request.cookies.get(policy.cookie_name)
    view = await auth_service.session(cookie)
    return SessionResponse.from_domain(view)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf), Depends(require_session_context)],
)
async def logout(
    request: Request,
    response: Response,
    principal=Depends(get_current_principal),
):
    policy = get_ingress_policy()
    auth_service = get_auth_service()
    cookie = request.cookies.get(policy.cookie_name) or ""
    csrf = request.headers.get("X-CSRF-Token", "")

    try:
        await auth_service.logout(principal, csrf, cookie)
    finally:
        response.delete_cookie(key=policy.cookie_name, path="/")
