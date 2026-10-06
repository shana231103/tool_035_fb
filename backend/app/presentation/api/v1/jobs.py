# File: backend/app/presentation/api/v1/jobs.py
import json
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from app.application.dtos.job_dtos import (
    BatchJobResponseDTO,
    BatchJobPageResponseDTO,
    CreateBatchJobRequestDTO,
)
from app.application.job_serialization import job_to_dto
from app.application.unit_of_work import IUnitOfWork
from app.application.use_cases.create_batch_job import CreateBatchJobUseCase
from app.application.use_cases.list_batch_jobs import ListBatchJobsUseCase
from app.application.use_cases.process_batch_queue import ProcessBatchQueueUseCase
from app.domain.exceptions.domain_exceptions import DomainError
from app.domain.exceptions.evidence_errors import EvidenceFileError
from app.presentation.api.proof_upload import read_proof_upload
from app.presentation.api.deps import (
    get_create_batch_job_use_case,
    get_list_batch_jobs_use_case,
    get_queue_orchestrator,
    get_unit_of_work,
)

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.post("", response_model=BatchJobResponseDTO, status_code=status.HTTP_201_CREATED)
async def create_job(
    name: str = Form(...),
    owner_profile_id: UUID = Form(...),
    target_urls_json: str = Form(..., description="JSON array of target URLs"),
    original_work_url: str = Form(...),
    preferred_country: Optional[str] = Form(None),
    concurrency: int = Form(1),
    delay_min: int = Form(0),
    delay_max: int = Form(0),
    custom_explanation: Optional[str] = Form(None),
    proof_file: Optional[UploadFile] = File(None),
    use_case: CreateBatchJobUseCase = Depends(get_create_batch_job_use_case),
):
    try:
        urls = json.loads(target_urls_json)
        if not isinstance(urls, list) or not urls:
            raise ValueError("target_urls_json must be a non-empty JSON list.")

        cmd = CreateBatchJobRequestDTO(
            name=name,
            owner_profile_id=owner_profile_id,
            target_urls=urls,
            original_work_url=original_work_url,
            preferred_country=preferred_country,  # type: ignore
            concurrency=concurrency,
            delay_min=delay_min,
            delay_max=delay_max,
            custom_explanation=custom_explanation,
        )

        proof_bytes, proof_name = await read_proof_upload(proof_file)

        return await use_case.execute(cmd, proof_file_bytes=proof_bytes, proof_filename=proof_name)
    except EvidenceFileError as error:
        codes = {"UNSUPPORTED_IMAGE": 415, "INVALID_IMAGE": 400, "TOO_LARGE": 413, "STORAGE_FAILED": 500}
        raise HTTPException(codes.get(error.reason, 500), "Proof image could not be accepted.") from None
    except (ValueError, DomainError):
        raise HTTPException(400, "Invalid batch job input.") from None
    finally:
        if proof_file:
            await proof_file.close()


@router.get("", response_model=List[BatchJobResponseDTO])
async def list_jobs(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    uow: IUnitOfWork = Depends(get_unit_of_work),
):
    async with uow:
        jobs = await uow.jobs.list_jobs(limit=limit, offset=offset)
        return [job_to_dto(j) for j in jobs]


@router.get("/page", response_model=BatchJobPageResponseDTO)
async def list_jobs_page(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    use_case: ListBatchJobsUseCase = Depends(get_list_batch_jobs_use_case),
):
    return await use_case.execute(limit, offset)


@router.get("/{job_id}", response_model=BatchJobResponseDTO)
async def get_job(job_id: UUID, uow: IUnitOfWork = Depends(get_unit_of_work)):
    async with uow:
        job = await uow.jobs.get_by_id(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Batch job not found.")
        return job_to_dto(job)


@router.post("/{job_id}/start")
async def start_job(
    job_id: UUID,
    orchestrator: ProcessBatchQueueUseCase = Depends(get_queue_orchestrator),
):
    try:
        await orchestrator.start_job(job_id)
    except DomainError as error:
        raise HTTPException(404, str(error)) from None
    except ValueError as error:
        raise HTTPException(409, str(error)) from None
    return {"message": f"Job {job_id} started."}


@router.post("/{job_id}/retry-failed")
async def retry_failed_tasks(
    job_id: UUID,
    orchestrator: ProcessBatchQueueUseCase = Depends(get_queue_orchestrator),
):
    try:
        count = await orchestrator.retry_failed_tasks(job_id)
    except DomainError as error:
        raise HTTPException(404, str(error)) from None
    except ValueError as error:
        raise HTTPException(409, str(error)) from None
    return {"retried_count": count, "message": "Failed tasks queued. Start Execution when ready."}


@router.post("/{job_id}/stop")
async def stop_job(
    job_id: UUID,
    orchestrator: ProcessBatchQueueUseCase = Depends(get_queue_orchestrator),
):
    try:
        await orchestrator.stop_job(job_id)
    except DomainError as error:
        raise HTTPException(404, str(error)) from None
    except ValueError as error:
        raise HTTPException(409, str(error)) from None
    return {"message": f"Job {job_id} stopped."}
