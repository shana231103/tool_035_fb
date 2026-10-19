# File: backend/app/presentation/api/v1/execution_status.py
"""Advisory availability combines durable slot, runtime and browser readiness."""

from fastapi import APIRouter, Depends
from app.domain.value_objects.operator_identity import OperatorPrincipal
from app.presentation.api.operator_auth import get_current_principal
from app.presentation.api.task_composition import get_task_admission_service
from app.presentation.api.deps import get_browser_control
from app.presentation.task_dtos import ExecutionAvailabilityDTO
from app.presentation.task_serialization import availability_to_dto

router = APIRouter(prefix="/execution", tags=["Execution"])


@router.get("/status", response_model=ExecutionAvailabilityDTO)
async def get_execution_status(
    principal: OperatorPrincipal = Depends(get_current_principal),
    admission=Depends(get_task_admission_service),
    browser=Depends(get_browser_control),
):
    try:
        availability = await admission.execution_status(principal)
        if availability.available:
            await browser.assert_ready()
        return availability_to_dto(availability)
    except Exception:
        return ExecutionAvailabilityDTO(available=False, reason="UNAVAILABLE")
