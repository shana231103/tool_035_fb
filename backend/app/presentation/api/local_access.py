# File: backend/app/presentation/api/local_access.py
import ipaddress
from fastapi import HTTPException, Request, Response, WebSocket
from starlette.responses import JSONResponse
from app.core.config import settings


class LocalAccessDenied(ValueError):
    def __init__(self, reason):
        super().__init__(reason)


class LocalAccessPolicy:
    def __init__(self, hosts, origins):
        self.hosts = frozenset(hosts)
        self.origins = frozenset(origins)

    def check(self, peer, host, origin, fetch_site, method, scheme, websocket=False):
        try:
            local = ipaddress.ip_address(peer).is_loopback if peer else False
        except ValueError:
            local = False
        if not local or host.lower() not in self.hosts:
            raise LocalAccessDenied("LOCAL_OPERATOR_REQUIRED")
        if fetch_site == "cross-site" or (origin is not None and origin not in self.origins):
            raise LocalAccessDenied("LOCAL_ORIGIN_REQUIRED")
        if websocket and origin is None:
            raise LocalAccessDenied("LOCAL_ORIGIN_REQUIRED")
        if method not in ("GET", "HEAD", "OPTIONS") and not origin and fetch_site != "same-origin":
            raise LocalAccessDenied("LOCAL_ORIGIN_REQUIRED")


def check_scope(scope, policy=None):
    headers = {}
    for name, value in scope.get("headers", []):
        name = name.decode("latin-1").lower()
        if name in ("host", "origin", "sec-fetch-site") and name in headers:
            raise LocalAccessDenied("AMBIGUOUS_HEADERS")
        headers[name] = value.decode("latin-1")
    peer = scope.get("client")
    (policy or LocalAccessPolicy(settings.local_allowed_hosts, settings.cors_origins)).check(
        peer[0] if peer else None, headers.get("host", ""), headers.get("origin"),
        headers.get("sec-fetch-site"), scope.get("method", "GET"),
        scope.get("scheme", "http"), scope["type"] == "websocket",
    )


class LocalAccessMiddleware:
    """Runs before routing and multipart parsing; uses the genuine transport peer."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        protected = (scope.get("path", "").startswith(("/api/v1/", "/static/")) or
                     scope.get("path") in ("/api/v1", "/ws"))
        if protected and scope["type"] in ("http", "websocket"):
            try:
                check_scope(scope)
            except LocalAccessDenied:
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                else:
                    response = JSONResponse({"detail": "Trusted local operator required."}, 403,
                                            headers={"Cache-Control": "no-store", "Pragma": "no-cache"})
                    await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


async def trusted_local_operator(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    try:
        check_scope(request.scope)
    except LocalAccessDenied:
        raise HTTPException(403, "Trusted local operator required.") from None


def trusted_local_websocket(websocket: WebSocket):
    check_scope(websocket.scope)
