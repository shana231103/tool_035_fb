# File: backend/app/infrastructure/mail/graph_transport.py
import asyncio
import json
import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import unquote, urlsplit

import httpx

from app.application.mailbox_lifecycle import MailboxLocks
from app.domain.exceptions.mailbox_errors import MailboxError
from app.domain.value_objects.mailbox_verification import MailboxBinding, ReadBudget
from app.infrastructure.mail.graph_response import (
    DEFAULT_RESPONSE_BYTES, MAX_RESPONSE_BYTES, MIN_RESPONSE_BYTES, read_bounded_response,
)
from app.infrastructure.mail.graph_denial import graph_denial_reason

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"


class GraphTransport:
    def __init__(self, auth, connections=None, *, client=None, http_timeout=10,
                 max_response_bytes=DEFAULT_RESPONSE_BYTES):
        if not 0 < http_timeout <= 10:
            raise ValueError("Invalid Graph timeout")
        if (type(max_response_bytes) is not int or
                not MIN_RESPONSE_BYTES <= max_response_bytes <= MAX_RESPONSE_BYTES):
            raise ValueError("Invalid Graph response limit")
        self.auth, self.connections = auth, connections
        self.client = client or httpx.AsyncClient(follow_redirects=False)
        self._synchronization = MailboxLocks()
        self._locks = self._synchronization.locks
        self.http_timeout, self.max_response_bytes, self.closed = http_timeout, max_response_bytes, False

    def _validate_url(self, url: str) -> None:
        try:
            parsed = urlsplit(url)
            path = unquote(parsed.path)
            valid = (parsed.scheme == "https" and parsed.hostname == "graph.microsoft.com"
                     and parsed.port in (None, 443) and not parsed.username and not parsed.password
                     and not parsed.fragment and path.startswith("/v1.0/")
                     and "\\" not in path and not any(p in (".", "..") for p in path.split("/")))
        except (TypeError, ValueError):
            valid = False
        if not valid:
            raise MailboxError("GRAPH_LINK_REJECTED")

    async def get(self, binding: MailboxBinding, url: str, deadline: float, budget: ReadBudget) -> dict:
        self._validate_url(url)
        if self.connections is not None:
            await self.connections.assert_ready(binding)
        remaining = min(deadline, budget.deadline) - budget.clock()
        if remaining <= 0:
            raise MailboxError("READ_BUDGET_EXHAUSTED")
        try:
            async with asyncio.timeout(remaining):
                async with self._synchronization.hold(binding.connection_id):
                    result = await self._request(binding.connection_id, url, deadline, budget, binding)
                    if self.connections is not None:
                        await self.connections.assert_ready(binding)
                    return result
        except TimeoutError:
            raise MailboxError("READ_BUDGET_EXHAUSTED") from None

    async def _request(self, connection_id, url, deadline, budget, binding=None):
        renewed, retries = False, 0
        token = None
        while True:
            if self.closed:
                raise MailboxError("DISCONNECTED")
            if binding is not None and self.connections is not None:
                await self.connections.assert_ready(binding)
            remaining = min(deadline, budget.deadline) - budget.clock()
            if remaining <= 0:
                raise MailboxError("READ_BUDGET_EXHAUSTED")
            budget.consume_request()
            if token is None:
                token = await self.auth.acquire_access_token(connection_id, deadline)
            try:
                status, headers, content = await read_bounded_response(
                    self.client, url, {"Authorization": "Bearer " + token,
                    "Accept-Encoding": "identity",
                    "Prefer": 'IdType="ImmutableId", outlook.body-content-type="text"'},
                    min(self.http_timeout, remaining), self.max_response_bytes)
            except httpx.HTTPError:
                if retries >= 3:
                    raise MailboxError("MAILBOX_UNAVAILABLE") from None
                await self._delay(2 ** retries + random.random(), deadline, budget)
                retries += 1
                continue
            if status == 401:
                if renewed:
                    raise MailboxError("AUTH_REQUIRED")
                token = await self.auth.acquire_access_token(connection_id, deadline, force_refresh=True)
                renewed = True
                continue
            if status == 403:
                raise MailboxError(graph_denial_reason(content, mailbox_operation="/me?" not in url))
            if status == 429 or 500 <= status <= 599:
                if retries >= 3:
                    raise MailboxError("THROTTLED" if status == 429 else "MAILBOX_UNAVAILABLE")
                delay = self._retry_after(headers.get("Retry-After")) if status == 429 else None
                await self._delay(delay if delay is not None else 2 ** retries + random.random(), deadline, budget)
                retries += 1
                continue
            if 300 <= status <= 399:
                raise MailboxError("GRAPH_LINK_REJECTED")
            if status != 200:
                raise MailboxError("MAILBOX_UNAVAILABLE")
            try:
                result = json.loads(content)
            except (ValueError, UnicodeError):
                raise MailboxError("GRAPH_PROTOCOL_ERROR") from None
            if not isinstance(result, dict):
                raise MailboxError("GRAPH_PROTOCOL_ERROR")
            if "@odata.nextLink" in result:
                self._validate_url(result["@odata.nextLink"])
            return result

    @staticmethod
    def _retry_after(value):
        if not value:
            return None
        try:
            seconds = float(value)
            return max(0, seconds) if seconds < float("inf") else None
        except ValueError:
            try:
                stamp = parsedate_to_datetime(value)
                if stamp.tzinfo is None:
                    return None
                return max(0, (stamp - datetime.now(timezone.utc)).total_seconds())
            except (ValueError, TypeError, OverflowError):
                return None

    @staticmethod
    async def _delay(seconds, deadline, budget):
        budget.check()
        remaining = min(deadline, budget.deadline) - budget.clock()
        if seconds >= remaining:
            raise MailboxError("THROTTLED")
        await asyncio.sleep(seconds)

    async def probe(self, connection_id: str) -> dict:
        deadline = time.monotonic() + 30
        budget = ReadBudget(10, 5, 1, deadline)
        async with asyncio.timeout(30):
            async with self._synchronization.hold(connection_id):
                identity = await self._request(connection_id, GRAPH_ROOT + "/me?$select=id,mail,userPrincipalName", deadline, budget)
                # Mail.ReadBasic cannot retrieve body; the successful body projection proves mailbox access.
                await self._request(connection_id, GRAPH_ROOT + "/me/mailFolders/inbox/messages?$top=1&$select=id,body", deadline, budget)
        return identity

    async def close(self) -> None:
        self.closed = True
        await self.client.aclose()
