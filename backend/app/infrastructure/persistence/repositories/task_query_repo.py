# File: backend/app/infrastructure/persistence/repositories/task_query_repo.py
"""SQLAlchemy implementation of ITaskQueries for read-only projections."""

import json
from datetime import datetime, timezone
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.task_queries import ITaskQueries, TaskReadModel
from app.domain.value_objects.enums import ProxyCountry, TaskStatus
from app.domain.value_objects.task_error_codes import public_task_error_code
from app.infrastructure.persistence.task_models import ReportTaskModel


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class SqlTaskQueryRepository(ITaskQueries):
    def __init__(self, session: AsyncSession, operator_id: UUID) -> None:
        self._session = session
        self._operator_id = operator_id

    def _to_read_model(self, m: ReportTaskModel) -> TaskReadModel:
        urls: Tuple[str, ...] = ()
        if m.target_urls_json:
            try:
                parsed = json.loads(m.target_urls_json)
                if isinstance(parsed, list):
                    urls = tuple(str(u) for u in parsed)
            except Exception:
                urls = ()
        if not urls and m.target_url:
            urls = (m.target_url,)

        status = TaskStatus(m.status)
        is_legacy = bool(m.legacy_read_only or m.legacy_batch_job_id)
        evidence = any(v is not None for v in (m.submitted_at, m.receipt_text, m.meta_case_number, m.screenshot_path))
        can_start = status == TaskStatus.DRAFT and not is_legacy and not evidence
        can_retry = (
            (status == TaskStatus.FAILED)
            and not is_legacy and not evidence
            and ((m.retry_count or 0) < (m.max_retries if m.max_retries is not None else 3))
        )
        can_stop = (
            status in (TaskStatus.DRAFT, TaskStatus.PREPARING, TaskStatus.RUNNING, TaskStatus.WAITING_EMAIL_CODE, TaskStatus.VERIFYING_EMAIL, TaskStatus.SUBMITTING)
        ) and not is_legacy

        return TaskReadModel(
            id=UUID(m.id),
            operator_id=UUID(m.operator_account_id),
            name=m.name or "Report Task",
            owner_profile_id=UUID(m.owner_profile_id) if m.owner_profile_id else None,
            preferred_country=(
                ProxyCountry(m.preferred_country) if m.preferred_country else None
            ),
            target_urls=urls,
            target_count=len(urls),
            original_url=m.original_url,
            explanation=m.explanation,
            status=status,
            version=m.version or 1,
            attempt_id=UUID(m.attempt_id) if m.attempt_id else None,
            retry_count=m.retry_count or 0,
            max_retries=m.max_retries or 3,
            created_at=_ensure_utc(m.created_at) or datetime.now(timezone.utc),
            updated_at=_ensure_utc(m.updated_at) or datetime.now(timezone.utc),
            completed_at=_ensure_utc(m.completed_at),
            meta_case_number=m.meta_case_number,
            receipt_text=m.receipt_text,
            screenshot_path=m.screenshot_path,
            error_message=m.error_message,
            legacy_read_only=is_legacy,
            display_summary=m.display_summary,
            submitted_at=_ensure_utc(m.submitted_at),
            has_submission_evidence=evidence,
            safe_error_code=public_task_error_code(
                status, m.error_message, has_submission_evidence=evidence,
            ),
            can_start=can_start,
            can_retry=can_retry,
            can_stop=can_stop,
        )

    async def list_tasks(
        self,
        limit: int,
        offset: int,
        statuses: Tuple[TaskStatus, ...] = (),
    ) -> Tuple[TaskReadModel, ...]:
        stmt = (
            select(ReportTaskModel)
            .where(ReportTaskModel.operator_account_id == str(self._operator_id))
            .order_by(ReportTaskModel.created_at.desc(), ReportTaskModel.id.desc())
            .offset(offset)
            .limit(limit)
        )
        if statuses:
            stmt = stmt.where(
                ReportTaskModel.status.in_([s.value for s in statuses])
            )
        res = await self._session.execute(stmt)
        models = res.scalars().all()
        return tuple(self._to_read_model(m) for m in models)

    async def get_detail(self, task_id: UUID) -> Optional[TaskReadModel]:
        stmt = select(ReportTaskModel).where(
            ReportTaskModel.operator_account_id == str(self._operator_id),
            ReportTaskModel.id == str(task_id),
        )
        res = await self._session.execute(stmt)
        m = res.scalar_one_or_none()
        return self._to_read_model(m) if m else None
