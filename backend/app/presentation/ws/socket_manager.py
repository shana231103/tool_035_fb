# File: backend/app/presentation/ws/socket_manager.py
import asyncio
import json
import math
from typing import Any, Optional
from uuid import UUID
from fastapi import WebSocket
from app.domain.value_objects.operator_identity import OperatorPrincipal
from app.presentation.ws.client_channel import ClientChannel


class WebSocketManager:
    def __init__(self, **kwargs):
        self._channels: dict[WebSocket, ClientChannel] = {}
        self._owned: dict[WebSocket, ClientChannel] = {}
        self._retiring: set[asyncio.Task] = set()
        self._authorizer = kwargs.pop("authorizer", None)
        self.configure(**kwargs)

    def set_authorizer(self, authorizer: Any) -> None:
        self._authorizer = authorizer

    def configure(
        self,
        *,
        max_clients: int = 32,
        queue_size: int = 32,
        max_payload_bytes: int = 65536,
        send_timeout: float = 2.0,
        close_timeout: float = 1.0,
        max_account_clients: int = 4,
    ) -> None:
        if self._owned or self._retiring:
            raise RuntimeError("Cannot configure WebSockets while clients are owned.")
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
            for value in (max_clients, queue_size, max_payload_bytes, max_account_clients)
        ):
            raise ValueError("WebSocket capacity limits must be positive integers.")
        if any(not math.isfinite(value) or value <= 0 for value in (send_timeout, close_timeout)):
            raise ValueError("WebSocket timeouts must be finite and positive.")
        self._max_clients, self._queue_size = max_clients, queue_size
        self._max_payload_bytes = max_payload_bytes
        self._send_timeout, self._close_timeout = send_timeout, close_timeout
        self._max_account_clients = max_account_clients
        self._closed = False

    def close_admission(self) -> None:
        self._closed = True

    async def _reject(self, websocket: WebSocket, code: int) -> bool:
        try:
            async with asyncio.timeout(self._close_timeout):
                await websocket.close(code=code)
        except Exception:
            pass
        return False

    async def connect(
        self, websocket: WebSocket, principal: Optional[OperatorPrincipal] = None
    ) -> bool:
        if websocket in self._owned:
            return websocket in self._channels
        if self._closed or len(self._owned) >= self._max_clients:
            return await self._reject(websocket, 1013)

        if principal is not None:
            acct_cnt = sum(
                1 for ch in self._owned.values()
                if ch.principal and ch.principal.operator_id == principal.operator_id
            )
            if acct_cnt >= self._max_account_clients:
                return await self._reject(websocket, 1013)

        channel = ClientChannel(
            websocket,
            self._queue_size,
            self._send_timeout,
            self._close_timeout,
            principal=principal,
            authorizer=self._authorizer,
            on_auth_failed=self._retire,
        )
        self._owned[websocket] = channel
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

    def get_active_principals(self) -> list[tuple[WebSocket, Optional[OperatorPrincipal]]]:
        return [(ws, ch.principal) for ws, ch in list(self._channels.items())]

    def retire_with_code(self, websocket: WebSocket, code: int) -> None:
        self._retire(websocket, code)

    async def close_session(self, session_id: UUID) -> None:
        for ws, ch in list(self._owned.items()):
            if ch.principal and ch.principal.session_id == session_id:
                self._retire(ws, 4401)

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

    def publish_json(
        self,
        message_or_owner: Any = None,
        message: Optional[dict[str, Any]] = None,
        *,
        owner: Optional[Any] = None,
    ) -> None:
        if message is not None:
            payload_dict = message
            target_owner = owner if owner is not None else message_or_owner
        else:
            payload_dict = message_or_owner
            target_owner = owner
            if target_owner is None and isinstance(payload_dict, dict):
                target_owner = payload_dict.get("operator_id") or payload_dict.get("owner")

        if target_owner is not None and not isinstance(target_owner, UUID):
            try:
                target_owner = UUID(str(target_owner))
            except (ValueError, TypeError):
                pass

        payload = json.dumps(payload_dict, default=str)
        oversized = len(payload.encode("utf-8")) > self._max_payload_bytes
        for websocket, channel in list(self._channels.items()):
            if target_owner is not None and channel.principal is not None:
                if channel.principal.operator_id != target_owner:
                    continue
            if oversized or not channel.offer(payload):
                self._retire(websocket, 1013)

    async def broadcast_json(self, message: dict[str, Any], *, owner: Optional[Any] = None) -> None:
        self.publish_json(message, owner=owner)

    async def shutdown(self) -> None:
        self.close_admission()
        if self._authorizer is not None:
            try:
                await self._authorizer.shutdown()
            except Exception:
                pass
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
            self._retiring.difference_update(retiring)
        if cancelled:
            raise asyncio.CancelledError


socket_manager = WebSocketManager()
