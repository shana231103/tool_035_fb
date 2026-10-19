# File: backend/app/presentation/api/hosted_policy.py
"""Ingress and security header policies for local development and hosted deployments."""

from typing import Optional, Set
from urllib.parse import urlparse
from app.domain.exceptions.operator_errors import IngressDeniedError


class IngressPolicy:
    """Enforces Host, Origin, and security preflight checks per deployment mode."""

    def __init__(
        self,
        mode: str = "local",
        public_origin: Optional[str] = None,
        allowed_hosts: Optional[Set[str]] = None,
        allowed_origins: Optional[Set[str]] = None,
    ):
        self.mode = mode.lower().strip()
        self.public_origin = public_origin.rstrip("/") if public_origin else None
        self.allowed_hosts = set(allowed_hosts or set())
        self.allowed_origins = set(allowed_origins or set())

        if self.public_origin:
            self.allowed_origins.add(self.public_origin)
            parsed = urlparse(self.public_origin)
            if parsed.netloc:
                self.allowed_hosts.add(parsed.netloc)

        if self.mode == "local":
            self.allowed_hosts.update({"127.0.0.1", "localhost", "testserver"})
            self.allowed_origins.update(
                {
                    "http://127.0.0.1",
                    "http://localhost",
                    "http://127.0.0.1:5173",
                    "http://localhost:5173",
                    "http://127.0.0.1:8000",
                    "http://localhost:8000",
                }
            )

    @property
    def cookie_name(self) -> str:
        return "__Host-operator_session" if self.mode == "hosted" else "operator_session_dev"

    @property
    def is_cookie_secure(self) -> bool:
        return self.mode == "hosted"

    def check_request(self, host: str, origin: Optional[str]) -> None:
        if not host:
            raise IngressDeniedError("Host header missing")

        clean_host = host.split(":")[0].lower()
        if self.allowed_hosts and clean_host not in self.allowed_hosts and host.lower() not in self.allowed_hosts:
            raise IngressDeniedError(f"Host '{host}' not permitted")

        if origin:
            clean_origin = origin.rstrip("/").lower()
            if self.mode == "hosted" and clean_origin not in self.allowed_origins:
                raise IngressDeniedError(f"Origin '{origin}' not permitted in hosted mode")

    def check_login_headers(self, origin: Optional[str], custom_header: Optional[str]) -> None:
        if custom_header != "1":
            raise IngressDeniedError("Missing required X-Operator-Login: 1 header")
        if not origin and self.mode == "hosted":
            raise IngressDeniedError("Origin header required for login")
        if origin:
            clean_origin = origin.rstrip("/").lower()
            if self.allowed_origins and clean_origin not in self.allowed_origins:
                raise IngressDeniedError(f"Login Origin '{origin}' not permitted")
