# File: backend/app/infrastructure/automation/adspower_client.py
import asyncio
import json
import logging
import time
import httpx
from app.infrastructure.automation.adspower_policy import AdsPowerPolicy
from app.infrastructure.automation.adspower_wire import (
    AdsPowerTransportError, CreatedProfile, StartedProfile, ProfileStatus,
    ProviderAck, ProfilePage, ProfileSummary, TransportCertainty, envelope, profile_id,
)

logger = logging.getLogger(__name__)


def log_request_failure(path, error, started_at):
    routes = {
        "/api/v2/browser-profile/list": "list_profiles",
        "/api/v2/browser-profile/create": "create_profile",
        "/api/v2/browser-profile/start": "start_profile",
        "/api/v2/browser-profile/active": "profile_status",
        "/api/v2/browser-profile/stop": "stop_profile",
        "/api/v2/browser-profile/delete": "delete_profile",
    }
    # Exception text can contain URLs, response bodies and API keys; never log it.
    logger.warning("AdsPower API failed: operation=%s error_type=%s elapsed_seconds=%.1f",
                   routes.get(path, "other"), type(error).__name__, time.monotonic() - started_at)


class AdsPowerClient:
    def __init__(self, settings, transport=None):
        self.settings = settings
        AdsPowerPolicy(settings)
        headers = {}
        key = settings.api_key.get_secret_value()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        self._http = httpx.AsyncClient(base_url=settings.api_base_url, headers=headers,
            timeout=httpx.Timeout(settings.read_timeout, connect=settings.connect_timeout),
            follow_redirects=False, trust_env=False, transport=transport)
        self._pace = asyncio.Lock()
        self._next_request = 0.0

    async def _request(self, method, path, *, payload=None, params=None, deadline=None):
        dispatched = False
        started_at = time.monotonic()
        try:
            async with asyncio.timeout(deadline or self.settings.read_timeout):
                async with self._pace:
                    delay = self._next_request - time.monotonic()
                    if delay > 0:
                        await asyncio.sleep(delay)
                    self._next_request = time.monotonic() + 1 / self.settings.api_rps
                dispatched = True
                # Lifecycle operations have their own budget (e.g. start_timeout).
                # Override the client's default read timeout so it cannot cut that budget short.
                timeout = httpx.Timeout(deadline or self.settings.read_timeout,
                                        connect=self.settings.connect_timeout)
                async with self._http.stream(method, path, json=payload, params=params,
                                             timeout=timeout) as response:
                    if response.status_code in {401, 403}:
                        raise AdsPowerTransportError("API_AUTH_REQUIRED", TransportCertainty.ACKNOWLEDGED)
                    if response.status_code == 429:
                        raise AdsPowerTransportError("API_RATE_LIMITED", TransportCertainty.ACKNOWLEDGED)
                    if response.status_code != 200:
                        raise AdsPowerTransportError()
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > self.settings.response_limit:
                            raise AdsPowerTransportError("API_INCOMPATIBLE")
                    return envelope(json.loads(body))
        except AdsPowerTransportError as error:
            log_request_failure(path, error, started_at)
            raise
        except (httpx.ConnectError, httpx.ConnectTimeout) as error:
            log_request_failure(path, error, started_at)
            raise AdsPowerTransportError(certainty=TransportCertainty.NOT_SENT) from None
        except (httpx.HTTPError, TimeoutError, ValueError, UnicodeError) as error:
            log_request_failure(path, error, started_at)
            certainty = TransportCertainty.MAY_HAVE_BEEN_SENT if dispatched else TransportCertainty.NOT_SENT
            raise AdsPowerTransportError(certainty=certainty) from None

    async def list_profiles(self, query):
        if query.page < 1 or not 1 <= query.limit <= 100:
            raise AdsPowerTransportError("API_INCOMPATIBLE", TransportCertainty.NOT_SENT)
        payload = {"group_id": query.group_id, "page": query.page, "limit": query.limit}
        if query.profile_ids:
            payload["profile_id"] = [profile_id(p) for p in query.profile_ids]
        data = await self._request("POST", "/api/v2/browser-profile/list", payload=payload)
        rows = data.get("list")
        if not isinstance(rows, list) or len(rows) > query.limit:
            raise AdsPowerTransportError("API_INCOMPATIBLE")
        try:
            items = tuple(ProfileSummary(profile_id(row["profile_id"]), str(row["group_id"]),
                          str(row.get("remark", "")), str(row.get("created_time", ""))) for row in rows)
        except (KeyError, TypeError):
            raise AdsPowerTransportError("API_INCOMPATIBLE") from None
        return ProfilePage(items, query.page)

    async def create_profile(self, draft):
        data = await self._request("POST", "/api/v2/browser-profile/create",
            payload=draft.payload(), deadline=self.settings.create_timeout)
        if "profile_no" not in data:
            raise AdsPowerTransportError("API_INCOMPATIBLE")
        return CreatedProfile(profile_id(data.get("profile_id")), str(data["profile_no"]))

    async def start_profile(self, ident):
        ident = profile_id(ident)
        data = await self._request("POST", "/api/v2/browser-profile/start",
            payload={"profile_id": ident, "last_opened_tabs": 0,
                     "launch_args": ["--start-maximized"]}, deadline=self.settings.start_timeout)
        try:
            endpoint, port = data["ws"]["puppeteer"], int(data["debug_port"])
            if not isinstance(endpoint, str):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise AdsPowerTransportError("API_INCOMPATIBLE") from None
        return StartedProfile(ident, endpoint, port)

    async def profile_status(self, ident):
        ident = profile_id(ident)
        data = await self._request("GET", "/api/v2/browser-profile/active", params={"profile_id": ident})
        if data.get("status") not in {"Active", "Inactive"}:
            raise AdsPowerTransportError("API_INCOMPATIBLE")
        return ProfileStatus(ident, data["status"] == "Active")

    async def stop_profile(self, ident):
        await self._request("POST", "/api/v2/browser-profile/stop", payload={"profile_id": profile_id(ident)})
        return ProviderAck()

    async def delete_profile(self, ident):
        await self._request("POST", "/api/v2/browser-profile/delete", payload={"profile_id": [profile_id(ident)]})
        return ProviderAck()

    async def aclose(self):
        await self._http.aclose()
