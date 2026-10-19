# File: backend/app/infrastructure/mail/auth_state.py
import asyncio
from dataclasses import dataclass, field


@dataclass(repr=False)
class AuthState:
    cache: object
    app: object | None = None
    account: dict | None = None
    flow: dict = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    worker: asyncio.Task | None = None
    active: bool = True
    reason: str | None = None


async def join_worker(task: asyncio.Task) -> None:
    """Keep ownership through repeated caller cancellation; drain worker errors."""
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
        except Exception:
            break
    if task.done() and not task.cancelled():
        task.exception()
    if cancelled:
        raise asyncio.CancelledError


def has_mail_read(result: dict) -> bool:
    return "mail.read" in {
        scope.casefold().removeprefix("https://graph.microsoft.com/")
        for scope in result.get("scope", "").split()
    }


def clear_auth_state(state: AuthState, cache_factory) -> None:
    try:
        if state.app is not None:
            for account in state.app.get_accounts():
                state.app.remove_account(account)
    finally:
        state.account = None
        state.flow.clear()
        state.app = None
        state.cache = cache_factory()
