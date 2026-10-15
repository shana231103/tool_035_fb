# File: backend/app/infrastructure/mail/oauth_refresh_exchange.py
import asyncio
from dataclasses import dataclass
import json
import math
import random
import time
import unicodedata

import httpx

from app.domain.exceptions.mailbox_errors import MailboxError
from app.domain.value_objects.mailbox_credentials import MailboxCredentials

AUTHORITY = "https://login.microsoftonline.com/common"
TOKEN_ENDPOINT = AUTHORITY + "/oauth2/v2.0/token"
SCOPES = ("https://graph.microsoft.com/User.Read", "https://graph.microsoft.com/Mail.Read")


@dataclass(frozen=True, repr=False)
class OAuthTokenGrant:
    access_token: str
    refresh_token: str | None
    expires_in: float
    granted_scopes: frozenset[str]


def remaining_budget(deadline: float, clock=time.monotonic) -> float:
    remaining = deadline - clock()
    if not math.isfinite(remaining) or remaining <= 0:
        raise MailboxError("MAILBOX_UNAVAILABLE")
    return remaining


def _valid_token(value) -> bool:
    return (isinstance(value, str) and bool(value) and
            not any(c.isspace() or unicodedata.category(c).startswith("C") for c in value))


def validate_grant(response: dict) -> OAuthTokenGrant:
    if not isinstance(response, dict):
        raise MailboxError("GRAPH_PROTOCOL_ERROR")
    expiry, scope = response.get("expires_in"), response.get("scope")
    try:
        ttl = float(expiry)
    except (ValueError, TypeError, OverflowError):
        raise MailboxError("GRAPH_PROTOCOL_ERROR") from None
    if (isinstance(expiry, bool) or not math.isfinite(ttl) or ttl <= 0
            or not _valid_token(response.get("access_token"))
            or not isinstance(response.get("token_type"), str)
            or response["token_type"].casefold() != "bearer"
            or not isinstance(scope, str) or not scope.strip()
            or ("refresh_token" in response and not _valid_token(response["refresh_token"]))):
        raise MailboxError("GRAPH_PROTOCOL_ERROR")
    scopes = frozenset(s.casefold().removeprefix("https://graph.microsoft.com/")
                       for s in scope.split())
    if "mail.read" not in scopes:
        raise MailboxError("MAIL_READ_REQUIRED")
    if "user.read" not in scopes:
        raise MailboxError("APP_CONSENT_REQUIRED")
    return OAuthTokenGrant(response["access_token"], response.get("refresh_token"), ttl, scopes)


def safe_oauth_reason(status: int, response: dict) -> str:
    error = response.get("error") if isinstance(response, dict) else None
    reasons = {"invalid_grant": "AUTH_REQUIRED", "invalid_client": "CONFIGURATION_REQUIRED",
               "unauthorized_client": "CONFIGURATION_REQUIRED", "invalid_scope": "APP_CONSENT_REQUIRED",
               "interaction_required": "APP_CONSENT_REQUIRED", "consent_required": "APP_CONSENT_REQUIRED"}
    if isinstance(error, str) and error in reasons:
        return reasons[error]
    return "THROTTLED" if status == 429 else "MAILBOX_UNAVAILABLE"


class OAuthRefreshExchange:
    """Public-client refresh only; provider responses never become diagnostics."""

    def __init__(self, *, token_endpoint=TOKEN_ENDPOINT, client=None, http_timeout=10,
                 max_response_bytes=65536, clock=time.monotonic, sleep=asyncio.sleep):
        if token_endpoint != TOKEN_ENDPOINT:
            raise ValueError("Unsupported Microsoft token endpoint")
        if (not 0 < http_timeout <= 10 or type(max_response_bytes) is not int
                or not 1 <= max_response_bytes <= 65536):
            raise ValueError("Invalid authentication limits")
        self.token_endpoint, self.http_timeout = token_endpoint, http_timeout
        self.max_response_bytes, self.clock, self.sleep = max_response_bytes, clock, sleep
        self.client = client or httpx.AsyncClient(follow_redirects=False)
        self.closed = False

    async def _request(self, credentials, deadline):
        timeout = min(self.http_timeout, remaining_budget(deadline, self.clock))
        data = {"grant_type": "refresh_token", "client_id": credentials.client_id,
                "refresh_token": credentials.refresh_token, "scope": " ".join(SCOPES)}
        async with asyncio.timeout(timeout):
            async with self.client.stream("POST", self.token_endpoint, data=data,
                    headers={"Accept-Encoding": "identity"}, timeout=timeout,
                    follow_redirects=False) as response:
                if 300 <= response.status_code <= 399:
                    raise MailboxError("GRAPH_PROTOCOL_ERROR")
                if response.headers.get("Content-Encoding", "identity").casefold() != "identity":
                    raise MailboxError("GRAPH_PROTOCOL_ERROR")
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(content) + len(chunk) > self.max_response_bytes:
                        raise MailboxError("GRAPH_PROTOCOL_ERROR")
                    content.extend(chunk)
                status, retry_after = response.status_code, response.headers.get("Retry-After")
        remaining_budget(deadline, self.clock)
        try:
            payload = json.loads(content)
        except (ValueError, UnicodeError, RecursionError):
            if status == 429 or 500 <= status <= 599:
                payload = {}
            else:
                raise MailboxError("GRAPH_PROTOCOL_ERROR") from None
        if not isinstance(payload, dict):
            raise MailboxError("GRAPH_PROTOCOL_ERROR")
        return status, retry_after, payload

    async def _delay(self, retries, retry_after, deadline):
        delay = 2 ** retries + random.random()
        try:
            requested = float(retry_after)
        except (ValueError, TypeError):
            requested = 0
        if math.isfinite(requested) and requested >= 0:
            delay = max(delay, requested)
        if delay >= remaining_budget(deadline, self.clock):
            raise MailboxError("MAILBOX_UNAVAILABLE")
        await self.sleep(delay)

    async def exchange(self, credentials: MailboxCredentials, deadline: float) -> OAuthTokenGrant:
        for retries in range(3):
            if self.closed:
                raise MailboxError("DISCONNECTED")
            try:
                status, retry_after, payload = await self._request(credentials, deadline)
            except (httpx.HTTPError, TimeoutError):
                if retries == 2:
                    raise MailboxError("MAILBOX_UNAVAILABLE") from None
                await self._delay(retries, None, deadline)
                continue
            if 200 <= status <= 299:
                return validate_grant(payload)
            if status != 429 and not 500 <= status <= 599:
                raise MailboxError(safe_oauth_reason(status, payload))
            if retries == 2:
                raise MailboxError("THROTTLED" if status == 429 else "MAILBOX_UNAVAILABLE")
            await self._delay(retries, retry_after, deadline)
        raise MailboxError("MAILBOX_UNAVAILABLE")

    async def close(self) -> None:
        self.closed = True
        await self.client.aclose()
