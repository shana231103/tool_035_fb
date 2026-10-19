# File: backend/app/infrastructure/network/proxy_endpoint_policy.py
"""DNS validation, SSRF protection, and IP pinning for proxies."""

import asyncio
import ipaddress
import socket
from datetime import datetime, timedelta, timezone
from typing import Optional, Set

from app.domain.entities.proxy_item import ProxyItem
from app.domain.exceptions.operator_errors import ProxyPolicyError
from app.domain.ports.operator_security import IProxyEndpointPolicy
from app.domain.value_objects.operator_identity import ValidatedProxyEndpoint


class ProxyEndpointPolicy(IProxyEndpointPolicy):
    def __init__(self, allowed_private_ips: Optional[Set[str]] = None):
        self._allowed_private_ips = allowed_private_ips or set()

    def _is_ip_safe(self, ip_str: str) -> bool:
        if ip_str in self._allowed_private_ips:
            return True
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False

        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False

        # Additional protection against cloud metadata
        if str(ip) == "169.254.169.254":
            return False

        return True

    async def prepare(
        self, proxy: ProxyItem, deadline: float
    ) -> ValidatedProxyEndpoint:
        proto = proxy.protocol.lower()
        if proto == "https":
            raise ProxyPolicyError("HTTPS proxy protocol is not supported")
        if proto not in ("http", "socks5", "socks5h"):
            raise ProxyPolicyError(f"Unsupported proxy protocol: {proto}")

        loop = asyncio.get_running_loop()
        now = datetime.now(timezone.utc)
        resolved_ips = []

        remaining = deadline - loop.time()
        if remaining <= 0:
            raise ProxyPolicyError(f"DNS resolution timed out for {proxy.host}")

        try:
            addr_info = await asyncio.wait_for(
                loop.getaddrinfo(
                    proxy.host,
                    proxy.port,
                    family=socket.AF_UNSPEC,
                    type=socket.SOCK_STREAM,
                ),
                timeout=remaining,
            )
            for item in addr_info:
                sockaddr = item[4]
                ip_str = sockaddr[0]
                try:
                    parsed = ipaddress.ip_address(ip_str)
                    if parsed.version == 6 and parsed.ipv4_mapped:
                        ip_str = str(parsed.ipv4_mapped)
                except ValueError:
                    pass
                if ip_str not in resolved_ips:
                    resolved_ips.append(ip_str)
        except asyncio.TimeoutError:
            raise ProxyPolicyError(f"DNS resolution timed out for {proxy.host}")
        except Exception as exc:
            raise ProxyPolicyError(f"DNS resolution failed for {proxy.host}: {exc}")

        if not resolved_ips:
            raise ProxyPolicyError(f"No IP addresses resolved for {proxy.host}")

        # Check every resolved IP address (SSRF & DNS rebinding protection)
        for ip_str in resolved_ips:
            if not self._is_ip_safe(ip_str):
                raise ProxyPolicyError(
                    f"Resolved IP {ip_str} for host {proxy.host} violates security policy"
                )

        selected_ip = resolved_ips[0]
        valid_until = now + timedelta(seconds=30)

        return ValidatedProxyEndpoint(
            protocol=proto,
            source_host=proxy.host,
            connect_ip=selected_ip,
            port=proxy.port,
            tls_server_name=None,
            resolved_at=now,
            valid_until=valid_until,
            credential_ref=None,
        )
