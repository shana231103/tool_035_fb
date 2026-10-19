# File: backend/app/infrastructure/auth/login_limits.py
"""In-memory rate limiter for login attempts with bounded cache and IP/user tracking."""

import time
from typing import Dict, Tuple
from app.domain.exceptions.operator_errors import LoginRateLimitError
from app.domain.ports.operator_security import ILoginLimits


class InMemoryLoginLimits(ILoginLimits):
    """Enforces rate limits on login attempts per normalized username and client IP."""

    def __init__(self, max_failures: int = 5, window_sec: float = 300.0, cooldown_sec: float = 60.0):
        self._max_failures = max_failures
        self._window_sec = window_sec
        self._cooldown_sec = cooldown_sec
        # key -> (failure_count, first_failure_time, locked_until)
        self._records: Dict[str, Tuple[int, float, float]] = {}
        self._max_cache = 10000

    def _prune_if_needed(self, now: float) -> None:
        if len(self._records) > self._max_cache:
            expired = [k for k, v in self._records.items() if now > v[1] + 900 and now > v[2]]
            for k in expired:
                self._records.pop(k, None)

    async def acquire(self, username_key: str, client_ip: str) -> None:
        now = time.monotonic()
        self._prune_if_needed(now)

        for key in (f"u:{username_key}", f"ip:{client_ip}"):
            if key in self._records:
                count, first_time, locked_until = self._records[key]
                if now < locked_until:
                    retry_after = max(1, int(locked_until - now))
                    raise LoginRateLimitError(
                        f"Rate limit exceeded. Try again in {retry_after}s",
                        retry_after=retry_after,
                    )

    def record_failure(self, username_key: str, client_ip: str) -> None:
        now = time.monotonic()
        for key in (f"u:{username_key}", f"ip:{client_ip}"):
            if key not in self._records:
                self._records[key] = (1, now, 0.0)
            else:
                count, first_time, locked_until = self._records[key]
                if now - first_time > self._window_sec:
                    self._records[key] = (1, now, 0.0)
                else:
                    new_count = count + 1
                    new_lock = now + self._cooldown_sec if new_count >= self._max_failures else 0.0
                    self._records[key] = (new_count, first_time, new_lock)

    def record_success(self, username_key: str, client_ip: str) -> None:
        self._records.pop(f"u:{username_key}", None)
        self._records.pop(f"ip:{client_ip}", None)
