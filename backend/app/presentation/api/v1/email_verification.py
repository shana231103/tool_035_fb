# File: backend/app/presentation/api/v1/email_verification.py
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from app.application.dtos.verification_dtos import VerificationSessionDTO
from app.application.use_cases.request_email_verification_code import RequestEmailVerificationCodeUseCase
from app.domain.ports.email_verification import VerificationError
from app.presentation.api.deps import get_verification_broker
from app.presentation.api.mailbox_guard import trusted_local_operator

router = APIRouter(prefix="/tasks", tags=["Email verification"])


@router.post("/{task_id}/verification/resend", status_code=202,
             dependencies=[Depends(trusted_local_operator)])
async def resend_code(task_id: UUID, dto: VerificationSessionDTO,
                      broker=Depends(get_verification_broker)):
    try:
        await RequestEmailVerificationCodeUseCase(broker).execute(str(task_id),
            str(dto.attempt_id), str(dto.challenge_id))
    except VerificationError:
        raise HTTPException(409, "Verification challenge changed, expired or is busy.") from None
    return {"accepted": True}
