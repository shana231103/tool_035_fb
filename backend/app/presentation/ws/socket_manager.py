# File: backend/app/presentation/ws/socket_manager.py
import asyncio
import json
import math
from typing import Any
from fastapi import WebSocket
from app.presentation.ws.client_channel import ClientChannel


class WebSocketManager:
    def __init__(self, *, max_clients=32, queue_size=32, max_payload_bytes=65536,
                 send_timeout=2.0, close_timeout=1.0):
        self._channels: dict[WebSocket, ClientChannel] = {}
        self._owned: dict[WebSocket, ClientChannel] = {}
        self._retiring: set[asyncio.Task] = set()
        self.configure(max_clients=max_clients, queue_size=queue_size,
                       max_payload_bytes=max_payload_bytes, send_timeout=send_timeout,
                       close_timeout=close_timeout)

    def configure(self, *, max_clients=32, queue_size=32, max_payload_bytes=65536,
                  send_timeout=2.0, close_timeout=1.0) -> None:
        if self._owned or self._retiring:
            raise RuntimeError("Cannot configure WebSockets while clients are owned.")
        if any(not isinstance(value, int) or isinstance(value, bool) or value <= 0
               for value in (max_clients, queue_size, max_payload_bytes)):
            raise ValueError("WebSocket capacity limits must be positive integers.")
        if any(not math.isfinite(value) or value <= 0
               for value in (send_timeout, close_timeout)):
            raise ValueError("WebSocket timeouts must be finite and positive.")
        self._max_clients, self._queue_size = max_clients, queue_size
        self._max_payload_bytes = max_payload_bytes
        self._send_timeout, self._close_timeout = send_timeout, close_timeout
        self._closed = False

    def close_admission(self) -> None:
        self._closed = True

    async def connect(self, websocket: WebSocket) -> bool:
        if websocket in self._owned:
            return websocket in self._channels
        if self._closed or len(self._owned) >= self._max_clients:
            try:
                async with asyncio.timeout(self._close_timeout):
                    await websocket.close(code=1013)
            except Exception:
                return False
            return False
        channel = ClientChannel(websocket, self._queue_size, self._send_timeout,
                                self._close_timeout)
        self._owned[websocket] = channel  # Reserve capacity before accepting.
        channel.accepting = asyncio.create_task(websocket.accept())
        try:
            await asyncio.shield(channel.accepting)
            if self._closed or channel.closed:
                self._retire(websocket, 1001)
                return False
            self._channels[websocket] = channel
            channel.writer = asyncio.create_task(channel.run())
            channel.writer.add_done_callback(lambda _: self._retire(websocket, 1013))
            return True
        except (Exception, asyncio.CancelledError):
            self._retire(websocket, 1013)
            raise

    def _retire(self, websocket: WebSocket, code: int) -> None:
        channel = self._owned.get(websocket)
        if channel is None or channel.closed:
            return
        channel.closed = True
        self._channels.pop(websocket, None)
        task = asyncio.create_task(self._finish_retirement(websocket, channel, code))
        self._retiring.add(task)
        task.add_done_callback(self._retiring.discard)

    async def _finish_retirement(self, websocket, channel, code) -> None:
        try:
            await channel.close(code)
        finally:
            self._owned.pop(websocket, None)

    def disconnect(self, websocket: WebSocket) -> None:
        self._retire(websocket, 1000)

    def publish_json(self, message: dict[str, Any]) -> None:
        """Serialize once and offer locally; never await transport or spawn per event."""
        payload = json.dumps(message, default=str)
        oversized = len(payload.encode("utf-8")) > self._max_payload_bytes
        for websocket, channel in list(self._channels.items()):
            if oversized or not channel.offer(payload):
                self._retire(websocket, 1013)

    async def broadcast_json(self, message: dict[str, Any]) -> None:
        self.publish_json(message)

    async def shutdown(self) -> None:
        self.close_admission()
        for websocket in list(self._owned):
            self._retire(websocket, 1001)
        cancelled = False
        while self._retiring:
            retiring = set(self._retiring)
            joined = asyncio.gather(*retiring, return_exceptions=True)
            while not joined.done():
                try:
                    await asyncio.shield(joined)
                except asyncio.CancelledError:
                    cancelled = True
            joined.result()
            # Already-finished tasks can make gather complete without yielding;
            # do not depend on scheduled done callbacks to empty the owner set.
            self._retiring.difference_update(retiring)
        if cancelled:
            raise asyncio.CancelledError


socket_manager = WebSocketManager()
