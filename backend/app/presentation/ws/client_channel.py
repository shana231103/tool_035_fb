# File: backend/app/presentation/ws/client_channel.py
import asyncio
from typing import Any, Callable, Optional
from fastapi import WebSocket
from app.domain.value_objects.operator_identity import OperatorPrincipal, SessionStatus


class ClientChannel:
    """Loop-confined FIFO with one writer; the manager owns retirement."""

    def __init__(
        self,
        socket: WebSocket,
        queue_size: int,
        send_timeout: float,
        close_timeout: float,
        principal: Optional[OperatorPrincipal] = None,
        authorizer: Any = None,
        on_auth_failed: Optional[Callable[[WebSocket, int], None]] = None,
    ):
        self.socket = socket
        self.queue: asyncio.Queue[str] = asyncio.Queue(maxsize=queue_size)
        self.send_timeout = send_timeout
        self.close_timeout = close_timeout
        self.principal = principal
        self.authorizer = authorizer
        self.on_auth_failed = on_auth_failed
        self.closed = False
        self.writer: asyncio.Task | None = None
        self.accepting: asyncio.Task | None = None

    def offer(self, payload: str) -> bool:
        if self.closed:
            return False
        try:
            self.queue.put_nowait(payload)
            return True
        except asyncio.QueueFull:
            return False

    async def run(self) -> None:
        while not self.closed:
            payload = await self.queue.get()
            try:
                if self.authorizer is not None and self.principal is not None:
                    try:
                        status = await self.authorizer.authorize(self.principal)
                    except Exception:
                        status = SessionStatus.UNKNOWN
                    if status in (SessionStatus.REVOKED, SessionStatus.EXPIRED):
                        if self.on_auth_failed:
                            self.on_auth_failed(self.socket, 4401)
                        return
                    if status != SessionStatus.VALID:
                        if self.on_auth_failed:
                            self.on_auth_failed(self.socket, 1013)
                        return

                async with asyncio.timeout(self.send_timeout):
                    await self.socket.send_text(payload)
            finally:
                self.queue.task_done()

    async def close(self, code: int) -> None:
        self.closed = True
        current = asyncio.current_task()
        owned = [
            task
            for task in (self.accepting, self.writer)
            if task is not None and task is not current
        ]
        for task in owned:
            if not task.done():
                task.cancel()
        await asyncio.gather(*owned, return_exceptions=True)
        while not self.queue.empty():
            self.queue.get_nowait()
            self.queue.task_done()
        try:
            async with asyncio.timeout(self.close_timeout):
                await self.socket.close(code=code)
        except Exception:
            return
