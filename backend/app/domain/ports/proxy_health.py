# File: backend/app/domain/ports/proxy_health.py
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ProxyCheckResult:
    is_alive: bool
    latency_ms: int
    detected_country: str = ""
    error: str = ""


class IProxyHealthService(ABC):
    @abstractmethod
    async def check_proxy(
        self,
        server_url: str,
        username: str = None,
        password: str = None,
    ) -> ProxyCheckResult:
        """Sends a lightweight probe through proxy to test latency and connectivity to Meta."""
        pass
