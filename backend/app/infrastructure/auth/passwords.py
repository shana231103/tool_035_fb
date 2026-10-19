# File: backend/app/infrastructure/auth/passwords.py
"""Argon2id password hasher adapter with bounded thread concurrency and queue capacity."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from app.domain.exceptions.operator_errors import HashBusyError
from app.domain.ports.operator_security import IPasswordHasher

# Fixed pre-computed valid Argon2id hash for constant-time dummy verification on nonexistent accounts
DUMMY_HASH = (
    "$argon2id$v=19$m=19456,t=2,p=1$c29tZXNhbHRmb3JkdW1teTE$kQy6c7k+02wW0K6d2oKj2V8W9y3B5Z4G1A2B3C4D5E0"
)


class Argon2PasswordHasher(IPasswordHasher):
    """Production Argon2id hasher with bounded active worker threads and queue limit."""

    def __init__(self, max_concurrent: int = 2, max_pending: int = 4):
        self._ph = PasswordHasher(
            time_cost=2,
            memory_cost=19456,
            parallelism=1,
            hash_len=32,
            salt_len=16,
        )
        self._max_concurrent = max_concurrent
        self._max_pending = max_pending
        self._active_count = 0
        self._pending_count = 0
        self._lock = asyncio.Lock()
        self._sem = asyncio.Semaphore(max_concurrent)
        self._executor = ThreadPoolExecutor(max_workers=max_concurrent)
        self._closing = False

    async def _run_owned(self, func: Callable[..., Any], *args: Any) -> Any:
        async with self._lock:
            if self._closing:
                raise HashBusyError("Password hasher is shutting down")
            if self._pending_count >= self._max_pending:
                raise HashBusyError("Password hashing capacity exceeded (queue full)")
            self._pending_count += 1

        try:
            try:
                async with asyncio.timeout(10.0):
                    await self._sem.acquire()
            except (TimeoutError, asyncio.CancelledError):
                raise HashBusyError("Password hashing wait timed out")
        finally:
            async with self._lock:
                self._pending_count -= 1

        loop = asyncio.get_running_loop()
        async with self._lock:
            self._active_count += 1

        future = loop.run_in_executor(self._executor, func, *args)

        def _on_thread_done(_: Any) -> None:
            self._sem.release()
            try:
                asyncio.run_coroutine_threadsafe(self._decrement_active(), loop)
            except RuntimeError:
                pass

        future.add_done_callback(_on_thread_done)

        try:
            async with asyncio.timeout(10.0):
                return await asyncio.shield(future)
        except TimeoutError:
            raise HashBusyError("Password hashing execution timed out")

    async def _decrement_active(self) -> None:
        async with self._lock:
            self._active_count -= 1

    async def hash(self, password: str) -> str:
        return await self._run_owned(self._ph.hash, password)

    async def verify(self, encoded: str, password: str) -> bool:
        target_hash = (
            encoded if (encoded and encoded.startswith("$argon2")) else DUMMY_HASH
        )
        result = await self._run_owned(self._sync_verify, target_hash, password)
        if target_hash == DUMMY_HASH:
            return False  # Dummy hash path never grants authentication
        return bool(result)

    def _sync_verify(self, encoded: str, password: str) -> bool:
        try:
            return self._ph.verify(encoded, password)
        except (VerifyMismatchError, VerificationError):
            return False
        except Exception:
            return False

    def needs_rehash(self, encoded: str) -> bool:
        try:
            return self._ph.check_needs_rehash(encoded)
        except Exception:
            return True

    async def shutdown(self) -> None:
        async with self._lock:
            self._closing = True
        self._executor.shutdown(wait=True)
