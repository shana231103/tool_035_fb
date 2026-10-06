# File: backend/app/domain/entities/proxy_item.py
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4
from app.domain.exceptions.domain_exceptions import InvalidProxyError
from app.domain.value_objects.enums import ProxyCountry, ProxyStatus


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ProxyItem:
    id: UUID
    protocol: str  # http, https, socks5
    host: str
    port: int
    country: ProxyCountry
    username: Optional[str] = None
    password: Optional[str] = None
    status: ProxyStatus = ProxyStatus.TESTING
    latency_ms: int = -1
    consecutive_failures: int = 0
    created_at: datetime = field(default_factory=_utc_now)
    last_checked_at: Optional[datetime] = None

    @classmethod
    def create(
        cls,
        host: str,
        port: int,
        country: ProxyCountry,
        protocol: str = "http",
        username: Optional[str] = None,
        password: Optional[str] = None,
        proxy_id: Optional[UUID] = None,
    ) -> "ProxyItem":
        if not host or not host.strip():
            raise InvalidProxyError("Proxy host is required.")
        if port <= 0 or port > 65535:
            raise InvalidProxyError(f"Invalid proxy port: {port}")

        return cls(
            id=proxy_id or uuid4(),
            protocol=protocol.lower().strip(),
            host=host.strip(),
            port=port,
            country=country,
            username=username.strip() if username else None,
            password=password.strip() if password else None,
            status=ProxyStatus.TESTING,
            latency_ms=-1,
            consecutive_failures=0,
            created_at=_utc_now(),
        )

    def mark_active(self, latency_ms: int) -> None:
        self.status = ProxyStatus.ACTIVE
        self.latency_ms = latency_ms
        self.consecutive_failures = 0
        self.last_checked_at = _utc_now()

    def mark_failed(self) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= 2:
            self.status = ProxyStatus.DEAD
        else:
            self.status = ProxyStatus.TESTING
        self.last_checked_at = _utc_now()

    def get_server_url(self) -> str:
        return f"{self.protocol}://{self.host}:{self.port}"
