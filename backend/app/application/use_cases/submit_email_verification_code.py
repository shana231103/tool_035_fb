# File: backend/app/application/use_cases/submit_email_verification_code.py
from app.domain.ports.email_verification import IVerificationBroker


class SubmitEmailVerificationCodeUseCase:
    def __init__(self, broker: IVerificationBroker):
        self._broker = broker

    async def execute(self, task_id: str, attempt_id: str, challenge_id: str, code: str) -> None:
        await self._broker.submit_code(task_id, attempt_id, challenge_id, code)
