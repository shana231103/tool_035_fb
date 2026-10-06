# File: backend/app/application/use_cases/request_email_verification_code.py
from app.domain.ports.email_verification import IVerificationBroker


class RequestEmailVerificationCodeUseCase:
    def __init__(self, broker: IVerificationBroker):
        self._broker = broker

    async def execute(self, task_id: str, attempt_id: str, challenge_id: str) -> None:
        await self._broker.request_resend(task_id, attempt_id, challenge_id)
