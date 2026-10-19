# File: backend/app/infrastructure/network/http_proxy_checker.py
import time
from datetime import datetime, timezone
from urllib.parse import quote
import httpx
from app.domain.ports.proxy_health import IProxyHealthService, ProxyCheckResult
from app.domain.value_objects.operator_identity import ValidatedProxyEndpoint
from app.domain.exceptions.operator_errors import ProxyPolicyError


class HttpProxyChecker(IProxyHealthService):
    def __init__(self, probe_url: str = "https://help.meta.com", timeout_seconds: float = 8.0):
        self._probe_url = probe_url
        self._timeout_seconds = timeout_seconds

    async def check_proxy(
        self,
        server_url: str = "",
        username: str | None = None,
        password: str | None = None,
        endpoint: ValidatedProxyEndpoint | None = None,
        credentials: object | None = None,
        deadline: float | None = None,
    ) -> ProxyCheckResult:
        if endpoint is not None:
            if datetime.now(timezone.utc) > endpoint.valid_until:
                raise ProxyPolicyError("Proxy endpoint has expired")
            proto = endpoint.protocol.lower()
            if proto == "https":
                raise ProxyPolicyError("HTTPS proxy protocol is not supported")
            user = getattr(credentials, "username", username)
            pwd = getattr(credentials, "password", password)
            if user and pwd:
                proxy_mount = f"{proto}://{quote(user, safe='')}:{quote(pwd, safe='')}@{endpoint.connect_ip}:{endpoint.port}"
            else:
                proxy_mount = f"{proto}://{endpoint.connect_ip}:{endpoint.port}"
        else:
            proxy_mount = server_url
            if username and password:
                parts = server_url.split("://", 1)
                scheme = parts[0] if len(parts) == 2 else "http"
                host_port = parts[1] if len(parts) == 2 else parts[0]
                proxy_mount = f"{scheme}://{quote(username, safe='')}:{quote(password, safe='')}@{host_port}"

        timeout = self._timeout_seconds
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return ProxyCheckResult(is_alive=False, latency_ms=-1, error="Probe deadline exceeded")
            timeout = min(self._timeout_seconds, remaining)

        start_time = time.perf_counter()
        try:
            async with httpx.AsyncClient(
                proxy=proxy_mount,
                timeout=timeout,
                verify=True,
                trust_env=False,
                follow_redirects=False,
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
