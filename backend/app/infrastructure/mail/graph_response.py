# File: backend/app/infrastructure/mail/graph_response.py
import httpx

from app.domain.exceptions.mailbox_errors import MailboxError


DEFAULT_RESPONSE_BYTES = 2 * 1024 * 1024
MIN_RESPONSE_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


async def read_bounded_response(client, url, headers, timeout, max_bytes):
    """Bound decoded bytes for all statuses before exposing content to JSON parsing."""
    async with client.stream("GET", url, headers=headers, timeout=timeout, follow_redirects=False) as response:
        if response.headers.get("Content-Encoding", "identity").strip().casefold() != "identity":
            raise MailboxError("GRAPH_PROTOCOL_ERROR")
        length = response.headers.get("Content-Length")
        if length is not None and (len(length) > 20 or not length.isascii() or
                                   not length.isdecimal() or int(length) > max_bytes):
            raise MailboxError("GRAPH_PROTOCOL_ERROR")
        content = bytearray()
        async for chunk in response.aiter_bytes():
            if len(chunk) > max_bytes - len(content):
                raise MailboxError("GRAPH_PROTOCOL_ERROR")
            content.extend(chunk)
        return response.status_code, httpx.Headers(response.headers), bytes(content)
