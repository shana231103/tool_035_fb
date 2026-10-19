# File: backend/app/presentation/api/v1/control_status.py
"""Control command status endpoint scoped to operator ownership."""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from app.application.unit_of_work import IUnitOfWorkFactory
from app.domain.value_objects.operator_identity import OperatorPrincipal
from app.presentation.api.operator_auth import get_current_principal
from app.presentation.api.operator_composition import get_scoped_uow_factory
from app.presentation.task_dtos import ControlViewDTO

router = APIRouter(
    prefix="/controls",
    tags=["Controls"],
)


@router.get("/{command_id}", response_model=ControlViewDTO)
async def get_control_status(
    command_id: UUID,
    principal: OperatorPrincipal = Depends(get_current_principal),
    uow_factory: IUnitOfWorkFactory = Depends(get_scoped_uow_factory),
):
    async with uow_factory.operator(principal.operator_id) as uow:
        receipt = await uow.controls.get_owned(principal.operator_id, command_id)
        if not receipt:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Control not found",
            )
        return ControlViewDTO(
            command_id=receipt.command_id,
            status=receipt.status.value,
            safe_code=receipt.result_code or "OK",
        )
