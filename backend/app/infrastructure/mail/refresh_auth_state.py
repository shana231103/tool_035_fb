# File: backend/app/infrastructure/mail/refresh_auth_state.py
import asyncio
from dataclasses import dataclass, field

from app.domain.value_objects.mailbox_credentials import MailboxAuthIdentity


@dataclass(repr=False)
class RefreshAuthState:
    email: str
    client_id: str
    refresh_token: str
    access_token: str = ""
    refresh_after: float = 0
    identity: MailboxAuthIdentity | None = None
    active: bool = True
    reason: str | None = None
    generation: int = 1
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    exchange_task: asyncio.Task | None = None

    def clear_secrets(self) -> None:
        self.email = self.client_id = self.refresh_token = self.access_token = ""
        self.refresh_after = 0
        self.identity = None


async def drain_exchange(task: asyncio.Task | None) -> None:
    if task is not None:
        await asyncio.gather(task, return_exceptions=True)
