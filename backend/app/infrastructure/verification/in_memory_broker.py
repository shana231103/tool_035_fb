# File: backend/app/infrastructure/verification/in_memory_broker.py
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from app.domain.ports.email_verification import (
    IVerificationBroker, VerificationCommand, VerificationError,
)


class InMemoryVerificationBroker(IVerificationBroker):
    """Ephemeral challenges, owned by one event loop. Codes only live in Futures."""

    def __init__(self) -> None:
        self._sessions: dict[str, dict] = {}

    async def open(self, task_id: str, attempt_id: str, email: str,
                   timeout: float, resend_supported: bool = False) -> dict:
        await self.close(task_id)
        now = datetime.now(timezone.utc)
        challenge = {
            "challenge_id": str(uuid4()), "attempt_id": attempt_id,
            "masked_email": email[:1] + "***@" + email.split("@")[-1],
            "requested_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=timeout)).isoformat(),
            "resend_supported": resend_supported,
        }
        self._sessions[task_id] = {
            "metadata": challenge, "deadline": asyncio.get_running_loop().time() + timeout,
            "command": asyncio.get_running_loop().create_future(),
        }
        return dict(challenge)

    def _get(self, task_id: str, attempt_id: str, challenge_id: str) -> dict:
        row = self._sessions.get(task_id)
        if (not row or row["metadata"]["attempt_id"] != attempt_id
                or row["metadata"]["challenge_id"] != challenge_id
                or asyncio.get_running_loop().time() >= row["deadline"]):
            raise VerificationError("Verification session expired or changed. Refresh task state.")
        return row

    async def wait(self, task_id: str, attempt_id: str, challenge_id: str) -> VerificationCommand:
        row = self._get(task_id, attempt_id, challenge_id)
        try:
            return await asyncio.wait_for(asyncio.shield(row["command"]),
                timeout=max(0, row["deadline"] - asyncio.get_running_loop().time()))
        except asyncio.TimeoutError:
            raise VerificationError("Email verification timed out.") from None

    async def assert_current(self, task_id: str, attempt_id: str, challenge_id: str) -> None:
        row = self._get(task_id, attempt_id, challenge_id)
        if row["command"].done():
            raise VerificationError("A verification command is already being processed.")

    async def submit_code(self, task_id: str, attempt_id: str, challenge_id: str, code: str) -> None:
        if not (4 <= len(code) <= 12 and code.isascii() and code.isdigit()):
            raise VerificationError("Code must contain 4 to 12 digits.")
        row = self._get(task_id, attempt_id, challenge_id)
        if row["command"].done():
            raise VerificationError("A verification command is already being processed.")
        row["command"].set_result(VerificationCommand("code", code))

    async def request_resend(self, task_id: str, attempt_id: str, challenge_id: str) -> None:
        row = self._get(task_id, attempt_id, challenge_id)
        if not row["metadata"]["resend_supported"]:
            raise VerificationError("The form does not currently support resending a code.")
        if row["command"].done():
            raise VerificationError("A verification command is already being processed.")
        row["command"].set_result(VerificationCommand("resend"))

    async def close(self, task_id: str) -> None:
        row = self._sessions.pop(task_id, None)
        if row and not row["command"].done():
            row["command"].cancel()
