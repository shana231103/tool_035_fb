# File: backend/app/presentation/ws/client_channel.py
import asyncio
from fastapi import WebSocket


class ClientChannel:
    """Loop-confined FIFO with one writer; the manager owns retirement."""

    def __init__(self, socket: WebSocket, queue_size: int, send_timeout: float,
                 close_timeout: float):
        self.socket = socket
        self.queue: asyncio.Queue[str] = asyncio.Queue(maxsize=queue_size)
        self.send_timeout = send_timeout
        self.close_timeout = close_timeout
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
                async with asyncio.timeout(self.send_timeout):
                    await self.socket.send_text(payload)
            finally:
                self.queue.task_done()

    async def close(self, code: int) -> None:
        self.closed = True
        current = asyncio.current_task()
        owned = [task for task in (self.accepting, self.writer)
                 if task is not None and task is not current]
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
            # Transport failure/timeout does not retain an admitted client.
            return
