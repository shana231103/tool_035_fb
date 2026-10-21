# File: backend/app/infrastructure/automation/adspower_wire.py
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class TransportCertainty(str, Enum):
    NOT_SENT = "NOT_SENT"
    MAY_HAVE_BEEN_SENT = "MAY_HAVE_BEEN_SENT"
    ACKNOWLEDGED = "ACKNOWLEDGED"


class AdsPowerTransportError(ValueError):
    def __init__(self, code="BROWSER_PROVIDER_UNAVAILABLE", certainty=TransportCertainty.MAY_HAVE_BEEN_SENT):
        self.code, self.certainty = code, certainty
        super().__init__(code)


def profile_id(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 128 or not value.isascii():
        raise AdsPowerTransportError("API_INCOMPATIBLE")
    if any(not (c.isalnum() or c in "_-.") for c in value):
        raise AdsPowerTransportError("API_INCOMPATIBLE")
    return value


@dataclass(frozen=True)
class CreatedProfile:
    profile_id: str
    profile_no: str


@dataclass(frozen=True)
class StartedProfile:
    profile_id: str
    endpoint: str = field(repr=False)
    debug_port: int


@dataclass(frozen=True)
class ProfileStatus:
    profile_id: str
    active: bool


@dataclass(frozen=True)
class ProviderAck:
    acknowledged: bool = True


@dataclass(frozen=True)
class ProfileSummary:
    profile_id: str
    group_id: str
    marker: str
    created_at: str = ""


@dataclass(frozen=True)
class ProfilePage:
    items: tuple[ProfileSummary, ...]
    page: int


@dataclass(frozen=True)
class ProfileQuery:
    group_id: str
    page: int = 1
    limit: int = 100
    profile_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProfileDraft:
    group_id: str
    name: str
    marker: str
    proxy: Any = field(default=None, repr=False)

    def payload(self):
        proxy = {"proxy_soft": "no_proxy"}
        if self.proxy:
            valid_until = getattr(self.proxy, "valid_until", None)
            if valid_until is not None and datetime.now(timezone.utc) > valid_until:
                raise AdsPowerTransportError("PROXY_ENDPOINT_EXPIRED")

            proto = getattr(self.proxy, "protocol", getattr(self.proxy, "scheme", "http")).lower()
            if proto == "https":
                raise AdsPowerTransportError("UNSUPPORTED_PROXY_PROTOCOL")

            connect_host = getattr(self.proxy, "connect_ip", getattr(self.proxy, "host", None))
            proxy = {"proxy_soft": "other", "proxy_type": proto,
                     "proxy_host": connect_host, "proxy_port": str(self.proxy.port)}
            username = getattr(self.proxy, "username", None)
            password = getattr(self.proxy, "password", None)
            if username is not None:
                proxy["proxy_user"] = username
            if password is not None:
                proxy["proxy_password"] = password
        return {"group_id": self.group_id, "name": self.name, "remark": self.marker,
                "fingerprint_config": {
                    "random_ua": {"ua_browser": ["chrome"], "ua_system_version": ["Windows 10"]},
                    "screen_resolution": "1366_768",
                    "webrtc": "disabled",
                    "language_switch": "0",
                    "language": ["en-US", "en"],
                    "page_language_switch": "0",
                    "page_language": "en-US",
                }, "user_proxy_config": proxy}


def envelope(value: Any) -> dict:
    if not isinstance(value, dict) or type(value.get("code")) is not int:
        raise AdsPowerTransportError("API_INCOMPATIBLE")
    if value["code"] != 0:
        raise AdsPowerTransportError(certainty=TransportCertainty.ACKNOWLEDGED)
    data = value.get("data", {})
    if not isinstance(data, dict):
        raise AdsPowerTransportError("API_INCOMPATIBLE")
    return data
