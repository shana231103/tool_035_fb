# File: backend/app/infrastructure/network/http_proxy_checker.py
import time
import httpx
from app.domain.ports.proxy_health import IProxyHealthService, ProxyCheckResult


class HttpProxyChecker(IProxyHealthService):
    def __init__(self, probe_url: str = "https://help.meta.com", timeout_seconds: float = 8.0):
        self._probe_url = probe_url
        self._timeout_seconds = timeout_seconds

    async def check_proxy(
        self,
        server_url: str,
        username: str = None,
        password: str = None,
    ) -> ProxyCheckResult:
        proxy_mount = server_url
        if username and password:
            parts = server_url.split("://", 1)
            scheme = parts[0] if len(parts) == 2 else "http"
            host_port = parts[1] if len(parts) == 2 else parts[0]
            proxy_mount = f"{scheme}://{username}:{password}@{host_port}"

        start_time = time.perf_counter()
        try:
            async with httpx.AsyncClient(
                proxy=proxy_mount,
                timeout=self._timeout_seconds,
                verify=True,
            ) as client:
                res = await client.get(self._probe_url)
                latency = int((time.perf_counter() - start_time) * 1000)
                if res.status_code < 500:
                    return ProxyCheckResult(
                        is_alive=True,
                        latency_ms=latency,
                        detected_country="",
                    )
                return ProxyCheckResult(
                    is_alive=False,
                    latency_ms=latency,
                    error=f"HTTP status error: {res.status_code}",
                )
        except ImportError:
            return ProxyCheckResult(
                is_alive=False,
                latency_ms=-1,
                error="Proxy checker configuration error: install HTTPX proxy dependencies (httpx[socks]).",
            )
        except Exception as e:
            return ProxyCheckResult(
                is_alive=False,
                latency_ms=-1,
                error=f"Connection failed: {str(e)}",
            )
