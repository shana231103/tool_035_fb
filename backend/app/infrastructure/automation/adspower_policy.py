# File: backend/app/infrastructure/automation/adspower_policy.py
import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit
from app.infrastructure.automation.adspower_wire import AdsPowerTransportError


def private_host(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    networks = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
    return ip.is_loopback or any(ip.version == ipaddress.ip_network(n).version
                                 and ip in ipaddress.ip_network(n) for n in networks)


class AdsPowerPolicy:
    def __init__(self, settings):
        self.settings = settings
        parsed = urlsplit(settings.api_base_url)
        if (parsed.scheme not in {"http", "https"} or not private_host(parsed.hostname or "")
                or parsed.username or parsed.password or parsed.path not in {"", "/"}
                or parsed.query or parsed.fragment):
            raise AdsPowerTransportError("BROWSER_ENDPOINT_REJECTED")
        try:
            parsed.port
        except ValueError:
            raise AdsPowerTransportError("BROWSER_ENDPOINT_REJECTED") from None
        if settings.endpoint_mode == "SAME_HOST" and not self._loopback(parsed.hostname):
            raise AdsPowerTransportError("BROWSER_ENDPOINT_REJECTED")
        if settings.endpoint_mode == "PRIVATE_REMOTE" and not private_host(settings.cdp_target_host):
            raise AdsPowerTransportError("BROWSER_ENDPOINT_REJECTED")

    @staticmethod
    def _loopback(host):
        return host == "localhost" or (host is not None and ipaddress.ip_address(host).is_loopback)

    def endpoint(self, endpoint: str, debug_port: int) -> str:
        try:
            value = urlsplit(endpoint)
            port = value.port
            if (value.scheme not in {"ws", "wss"} or value.username or value.password
                    or value.query or value.fragment or port != debug_port
                    or not self.settings.debug_port_min <= debug_port <= self.settings.debug_port_max
                    or not re.fullmatch(r"/devtools/browser/[A-Za-z0-9_-]{1,128}", value.path)):
                raise ValueError
            if self.settings.endpoint_mode == "SAME_HOST":
                if not self._loopback(value.hostname):
                    raise ValueError
                return endpoint
            if value.hostname != self.settings.cdp_source_host:
                raise ValueError
            host = self.settings.cdp_target_host
            netloc = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
            return urlunsplit((value.scheme, netloc, value.path, "", ""))
        except (ValueError, TypeError):
            raise AdsPowerTransportError("BROWSER_ENDPOINT_REJECTED") from None
