# File: backend/app/infrastructure/automation/adspower_wire.py
from dataclasses import dataclass, field
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
            proxy = {"proxy_soft": "other", "proxy_type": self.proxy.scheme,
                     "proxy_host": self.proxy.host, "proxy_port": str(self.proxy.port)}
            if self.proxy.username is not None:
                proxy["proxy_user"] = self.proxy.username
            if self.proxy.password is not None:
                proxy["proxy_password"] = self.proxy.password
        return {"group_id": self.group_id, "name": self.name, "remark": self.marker,
                "fingerprint_config": {"webrtc": "disabled", "language_switch": "1",
                                       "languages": ["en-US", "en"]},
                "user_proxy_config": proxy}


def envelope(value: Any) -> dict:
    if not isinstance(value, dict) or type(value.get("code")) is not int:
        raise AdsPowerTransportError("API_INCOMPATIBLE")
    if value["code"] != 0:
        raise AdsPowerTransportError(certainty=TransportCertainty.ACKNOWLEDGED)
    data = value.get("data", {})
    if not isinstance(data, dict):
        raise AdsPowerTransportError("API_INCOMPATIBLE")
    return data
