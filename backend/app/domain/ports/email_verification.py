# File: backend/app/domain/ports/email_verification.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class VerificationError(ValueError):
    """A challenge is expired, stale, busy or unavailable."""


@dataclass(frozen=True)
class VerificationCommand:
    kind: str
    code: str = field(default="", repr=False)


class IVerificationBroker(ABC):
    @abstractmethod
    async def assert_current(self, task_id: str, attempt_id: str, challenge_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def open(self, task_id: str, attempt_id: str, email: str,
                   timeout: float, resend_supported: bool = False) -> dict:
        raise NotImplementedError

    @abstractmethod
    async def wait(self, task_id: str, attempt_id: str, challenge_id: str) -> VerificationCommand:
        raise NotImplementedError

    @abstractmethod
    async def submit_code(self, task_id: str, attempt_id: str, challenge_id: str, code: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def request_resend(self, task_id: str, attempt_id: str, challenge_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def close(self, task_id: str) -> None:
        raise NotImplementedError
