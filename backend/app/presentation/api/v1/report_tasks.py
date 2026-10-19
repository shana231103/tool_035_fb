# File: backend/app/presentation/api/v1/report_tasks.py
"""Presentation API endpoints for Standalone ReportTask queries and lifecycle edits."""

import json
from typing import Optional
from uuid import UUID
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)

from app.application.task_admission import TaskAdmissionService
from app.application.task_records import (
    CreateTaskCommand,
    EvidenceInput,
    RetryTaskCommand,
)
from app.application.use_cases.create_report_task import CreateReportTaskUseCase
from app.application.use_cases.list_report_tasks import ListReportTasksUseCase
from app.domain.exceptions.domain_exceptions import DomainError, EntityNotFoundError
from app.domain.value_objects.enums import ProxyCountry
from app.domain.value_objects.operator_identity import OperatorPrincipal
from app.presentation.api.operator_auth import (
    get_current_principal,
    require_csrf,
    require_session_context,
)
from app.presentation.api.proof_upload import read_proof_upload
from app.presentation.api.task_composition import (
    get_create_task_use_case,
    get_list_tasks_use_case,
    get_task_admission_service,
)
from app.presentation.task_dtos import (
    RetryTaskRequest,
    TaskPageDTO,
    TaskViewDTO,
)
from app.presentation.task_serialization import (
    task_page_to_dto,
    task_view_to_dto,
)
from app.presentation.task_http_errors import task_http_error

router = APIRouter(
    prefix="/tasks",
    tags=["Tasks"],
)


@router.post("", response_model=TaskViewDTO, status_code=status.HTTP_201_CREATED)
async def create_task(
    name: str = Form(..., min_length=1, max_length=255),
    owner_profile_id: UUID = Form(...),
    target_urls_json: str = Form(..., description="JSON array of 1..30 URLs"),
    original_work_url: str = Form(...),
    preferred_country: Optional[str] = Form(None),
    custom_explanation: Optional[str] = Form(None),
    proof: Optional[UploadFile] = File(None),
    principal: OperatorPrincipal = Depends(get_current_principal),
    _csrf=Depends(require_csrf),
    _ctx=Depends(require_session_context),
    use_case: CreateReportTaskUseCase = Depends(get_create_task_use_case),
):
    try:
        urls = json.loads(target_urls_json)
        if not isinstance(urls, list):
            raise ValueError("target_urls_json must be a JSON array of URLs.")
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid target URLs JSON.",
        )

    if len(urls) < 1 or len(urls) > 30:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Target URLs count must be between 1 and 30, got {len(urls)}.",
        )

    proof_content, proof_filename = await read_proof_upload(proof)
    evidence_input = None
    if proof_content and proof_filename:
        evidence_input = EvidenceInput(
            filename=proof_filename, content=proof_content
        )

    country_val = None
    if preferred_country:
        try:
            country_val = ProxyCountry(preferred_country)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid preferred country.",
            )

    command = CreateTaskCommand(
        name=name,
        target_urls=tuple(urls),
        original_url=original_work_url,
        explanation=custom_explanation or "",
        owner_profile_id=owner_profile_id,
        preferred_country=country_val,
    )

    try:
        task_view = await use_case.execute(
            principal, command, proof=evidence_input
        )
        return task_view_to_dto(task_view)
    except EntityNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    except (DomainError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid task input."
        )
    except Exception as error:
        raise task_http_error(error) from None


@router.get("", response_model=TaskPageDTO)
async def list_tasks(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    principal: OperatorPrincipal = Depends(get_current_principal),
    use_case: ListReportTasksUseCase = Depends(get_list_tasks_use_case),
):
    page = await use_case.execute(
        owner=principal.operator_id, limit=limit, offset=offset
    )
    return task_page_to_dto(page)


@router.get("/{task_id}", response_model=TaskViewDTO)
async def get_task_detail(
    task_id: UUID,
    principal: OperatorPrincipal = Depends(get_current_principal),
    use_case: ListReportTasksUseCase = Depends(get_list_tasks_use_case),
):
    detail = await use_case.detail(owner=principal.operator_id, task_id=task_id)
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    return task_view_to_dto(detail)


@router.post("/{task_id}/retry", response_model=TaskViewDTO)
async def retry_task(
    task_id: UUID,
    req: RetryTaskRequest,
    principal: OperatorPrincipal = Depends(get_current_principal),
    _csrf=Depends(require_csrf),
    _ctx=Depends(require_session_context),
    admission: TaskAdmissionService = Depends(get_task_admission_service),
):
    try:
        command = RetryTaskCommand(task_id=task_id, expected_version=req.expected_version)
        task_view = await admission.prepare_retry(principal, command)
        return task_view_to_dto(task_view)
    except Exception as error:
        raise task_http_error(error) from None

