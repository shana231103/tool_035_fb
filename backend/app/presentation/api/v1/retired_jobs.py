# File: backend/app/presentation/api/v1/retired_jobs.py
"""Retired batch jobs routes returning HTTP 410 Gone with zero effects."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from app.presentation.api.operator_auth import (
    get_current_principal,
    require_csrf,
    require_session_context,
)

router = APIRouter(
    prefix="/jobs",
    tags=["Jobs"],
)

_GONE_DETAIL = "Batch jobs have been retired in Phase 004. Use /tasks instead."


@router.post("", status_code=status.HTTP_410_GONE)
@router.post("/{path:path}", status_code=status.HTTP_410_GONE)
async def retired_jobs_mutation(
    request: Request,
    _principal=Depends(get_current_principal),
    _csrf=Depends(require_csrf),
    _ctx=Depends(require_session_context),
):
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=_GONE_DETAIL)


@router.get("", status_code=status.HTTP_410_GONE)
@router.get("/{path:path}", status_code=status.HTTP_410_GONE)
async def retired_jobs_read(
    request: Request,
    _principal=Depends(get_current_principal),
):
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=_GONE_DETAIL)
