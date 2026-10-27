# File: backend/app/presentation/api/v1/bulk_jobs.py
import json
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from app.application.bulk_import_models import BulkImportError
from app.presentation.api.bulk_composition import (
    get_bulk_create, get_bulk_preview, get_bulk_review, get_bulk_settlement,
)
from app.presentation.api.mailbox_guard import trusted_local_operator
from app.presentation.bulk_job_dtos import BulkCreateRequestDTO, BulkPreviewRequestDTO

HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}
router = APIRouter(prefix="/jobs", tags=["Bulk Jobs"],
                   dependencies=[Depends(trusted_local_operator)])


async def bounded_body(request, model):
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 4194304:
            raise HTTPException(413, "IMPORT_LIMIT_EXCEEDED", headers=HEADERS)
        body.extend(chunk)
    try:
        return model.model_validate(json.loads(body))
    except (ValidationError, ValueError, UnicodeError):
        raise HTTPException(422, "Invalid request.", headers=HEADERS) from None


def _error_response(error):
    reasons = {"ORDER_FORMAT_INVALID", "ORDER_URL_INVALID", "TOO_MANY_TARGETS",
               "DUPLICATE_ORDER", "IMPORT_LIMIT_EXCEEDED", "MAIL_ROW_INVALID", "MAIL_DUPLICATE"}
    body = {"detail": error.reason}
    errors = [{"source_line": item.source_line, "reason": item.reason} for item in error.errors
              if type(item.source_line) is int and item.source_line > 0 and item.reason in reasons]
    if errors:
        body["errors"] = errors
    return JSONResponse(body, status_code=error.status_code, headers=HEADERS)


def private_response(response):
    response.headers.update(HEADERS)


@router.post("/bulk/preview")
async def preview_bulk(request: Request, response: Response, use_case=Depends(get_bulk_preview)):
    private_response(response)
    command = (await bounded_body(request, BulkPreviewRequestDTO)).to_command()
    try:
        return await use_case.execute(command)
    except BulkImportError as error:
        return _error_response(error)
    except ValueError:
        raise HTTPException(422, "Invalid request.", headers=HEADERS) from None


@router.post("/bulk")
async def create_bulk(request: Request, response: Response, settlement=Depends(get_bulk_settlement)):
    private_response(response)
    command = (await bounded_body(request, BulkCreateRequestDTO)).to_command()
    try:
        result = await settlement.submit(command)
        response.status_code = 200 if result.replayed else 201
        return result
    except BulkImportError as error:
        return _error_response(error)
    except ValueError:
        raise HTTPException(422, "Invalid request.", headers=HEADERS) from None


@router.get("/bulk/{import_id}")
async def lookup_bulk(import_id: UUID, response: Response, use_case=Depends(get_bulk_create)):
    private_response(response)
    result = await use_case.lookup(import_id)
    if result is None:
        raise HTTPException(404, "IMPORT_NOT_FOUND", headers=HEADERS)
    return result


@router.post("/{job_id}/bulk-review")
async def review_bulk(job_id: UUID, response: Response, use_case=Depends(get_bulk_review)):
    private_response(response)
    try:
        return await use_case.review_job(job_id)
    except BulkImportError as error:
        return _error_response(error)
