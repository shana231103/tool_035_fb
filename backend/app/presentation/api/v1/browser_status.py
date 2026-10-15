# File: backend/app/presentation/api/v1/browser_status.py
from uuid import UUID
from fastapi import APIRouter, Body, Depends, HTTPException
from app.application.browser_readiness import BrowserReadinessUseCase, BrowserCleanupUseCase
from app.domain.exceptions.browser_errors import BrowserError
from app.domain.exceptions.domain_exceptions import EntityNotFoundError
from app.presentation.api.local_access import trusted_local_operator
from app.presentation.api.browser_deps import get_browser_readiness_use_case, get_browser_cleanup_use_case
from app.presentation.api.browser_status_dtos import BrowserStatusResponseDTO, BrowserCleanupResponseDTO

router = APIRouter(prefix="/browser", tags=["Browser"], dependencies=[Depends(trusted_local_operator)])


@router.get("/status", response_model=BrowserStatusResponseDTO)
async def browser_status(task_id: UUID | None = None,
                         use_case: BrowserReadinessUseCase = Depends(get_browser_readiness_use_case)):
    try:
        return BrowserStatusResponseDTO.from_view(await use_case.execute(task_id))
    except EntityNotFoundError:
        raise HTTPException(404, detail="Report task not found.") from None
    except BrowserError as error:
        raise HTTPException(409, detail=error.code) from None


@router.post("/cleanup/{operation_id}/retry", response_model=BrowserCleanupResponseDTO)
async def retry_browser_cleanup(operation_id: UUID, payload: dict = Body(default_factory=dict),
                                use_case: BrowserCleanupUseCase = Depends(get_browser_cleanup_use_case)):
    if payload:
        raise HTTPException(422, detail="Invalid request.")
    try:
        return BrowserCleanupResponseDTO.from_outcome(await use_case.retry(operation_id))
    except (EntityNotFoundError, LookupError):
        raise HTTPException(404, detail="Browser operation not found.") from None
    except BrowserError as error:
        raise HTTPException(409, detail=error.code) from None
