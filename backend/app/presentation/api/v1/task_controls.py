# File: backend/app/presentation/api/v1/task_controls.py
"""Explicit task commands and owner-scoped admission receipt queries."""

from uuid import UUID
from fastapi import APIRouter, Depends, status
from app.application.task_records import StartTaskCommand, StopTaskCommand
from app.domain.value_objects.operator_identity import OperatorPrincipal
from app.presentation.api.operator_auth import (
    get_current_principal, require_csrf, require_session_context,
)
from app.presentation.api.task_composition import (
    get_operator_controls, get_task_admission_service, get_task_command_queries,
)
from app.presentation.task_dtos import (
    ControlViewDTO, StartReceiptDTO, StartTaskRequest, StopTaskRequest,
)
from app.presentation.task_http_errors import task_http_error
from app.presentation.task_serialization import control_view_to_dto, start_receipt_to_dto

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.post("/{task_id}/start", response_model=StartReceiptDTO,
             status_code=status.HTTP_202_ACCEPTED)
async def start_task(
    task_id: UUID, req: StartTaskRequest,
    principal: OperatorPrincipal = Depends(get_current_principal),
    _csrf=Depends(require_csrf), _ctx=Depends(require_session_context),
    admission=Depends(get_task_admission_service),
):
    try:
        command = StartTaskCommand(command_id=req.command_id, task_id=task_id,
                                   expected_version=req.expected_version)
        return start_receipt_to_dto(await admission.start(principal, command))
    except Exception as error:
        raise task_http_error(error) from None


@router.get("/{task_id}/starts/{command_id}", response_model=StartReceiptDTO)
async def get_start_receipt(
    task_id: UUID, command_id: UUID,
    principal: OperatorPrincipal = Depends(get_current_principal),
    queries=Depends(get_task_command_queries),
):
    try:
        return start_receipt_to_dto(
            await queries.get_start(principal, task_id, command_id)
        )
    except Exception as error:
        raise task_http_error(error) from None


@router.post("/{task_id}/stop", response_model=ControlViewDTO,
             status_code=status.HTTP_202_ACCEPTED)
async def stop_task(
    task_id: UUID, req: StopTaskRequest,
    principal: OperatorPrincipal = Depends(get_current_principal),
    _csrf=Depends(require_csrf), _ctx=Depends(require_session_context),
    controls=Depends(get_operator_controls),
):
    try:
        command = StopTaskCommand(
            command_id=req.command_id, task_id=task_id,
            expected_version=req.expected_version, attempt_id=req.attempt_id,
        )
        return control_view_to_dto(await controls.stop_task(principal, command))
    except Exception as error:
        raise task_http_error(error) from None
