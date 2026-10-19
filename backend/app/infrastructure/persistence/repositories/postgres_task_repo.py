# File: backend/app/infrastructure/persistence/repositories/postgres_task_repo.py
"""SQLAlchemy implementation of IReportTaskRepository for standalone tasks."""

import json
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.report_task import ReportTask
from app.domain.exceptions.domain_exceptions import LegacyTaskReadOnlyError
from app.domain.exceptions.task_errors import StaleVersionError
from app.domain.ports.repositories import IReportTaskRepository
from app.domain.value_objects.enums import ProxyCountry, TaskStatus
from app.domain.value_objects.explanation import ExplanationText
from app.domain.value_objects.original_url import OriginalUrl
from app.domain.value_objects.report_targets import ReportTargets
from app.domain.value_objects.target_url import TargetUrl
from app.infrastructure.persistence.task_models import ReportTaskModel


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class PostgresTaskRepository(IReportTaskRepository):
    def __init__(self, session: AsyncSession, operator_id: Optional[UUID] = None):
        self._session = session
        self._operator_id = operator_id

    @property
    def operator_id(self) -> Optional[UUID]:
        return self._operator_id

    def _model_to_entity(self, m: ReportTaskModel) -> ReportTask:
        if m.legacy_read_only or m.legacy_batch_job_id:
            raise LegacyTaskReadOnlyError(
                f"Task {m.id} is an archival legacy task and cannot be loaded as a runnable aggregate"
            )
        urls: List[str] = []
        if m.target_urls_json:
            try:
                parsed = json.loads(m.target_urls_json)
                if isinstance(parsed, list):
                    urls = [str(u) for u in parsed]
            except Exception:
                urls = []
        if not urls and m.target_url:
            urls = [m.target_url]

        targets = (
            ReportTargets.from_urls(urls)
            if urls
            else ReportTargets.from_urls(["https://www.facebook.com/fallback/posts/1"])
        )

        return ReportTask(
            id=UUID(m.id),
            operator_id=UUID(m.operator_account_id),
            owner_profile_id=UUID(m.owner_profile_id) if m.owner_profile_id else UUID("00000000-0000-0000-0000-000000000000"),
            name=m.name or "Report Task",
            targets=targets,
            original_url=OriginalUrl(url=m.original_url),
            explanation=ExplanationText(content=m.explanation),
            preferred_country=ProxyCountry(m.preferred_country) if m.preferred_country else None,
            status=TaskStatus(m.status),
            version=m.version or 1,
            run_version=m.run_version,
            attempt_id=UUID(m.attempt_id) if m.attempt_id else None,
            last_start_command_id=UUID(m.last_start_command_id) if m.last_start_command_id else None,
            retry_count=m.retry_count or 0,
            max_retries=m.max_retries or 3,
            proxy_id=UUID(m.proxy_id) if m.proxy_id else None,
            created_at=_ensure_utc(m.created_at) or datetime.now(timezone.utc),
            updated_at=_ensure_utc(m.updated_at) or datetime.now(timezone.utc),
            completed_at=_ensure_utc(m.completed_at),
            input_snapshot=m.input_snapshot or {},
            verification=m.verification or {},
            submitted_at=_ensure_utc(m.submitted_at),
            receipt_text=m.receipt_text,
            meta_case_number=m.meta_case_number,
            screenshot_path=m.screenshot_path,
            error_message=m.error_message,
        )

    async def get_by_id(self, task_id: UUID) -> Optional[ReportTask]:
        stmt = select(ReportTaskModel).where(ReportTaskModel.id == str(task_id)).execution_options(populate_existing=True)
        if self._operator_id:
            stmt = stmt.where(ReportTaskModel.operator_account_id == str(self._operator_id))
        res = await self._session.execute(stmt)
        m = res.scalar_one_or_none()
        return self._model_to_entity(m) if m else None

    async def insert(self, task: ReportTask) -> None:
        target_urls = list(task.targets.urls)
        model = ReportTaskModel(
            id=str(task.id),
            operator_account_id=str(task.operator_id),
            name=task.name,
            owner_profile_id=str(task.owner_profile_id) if task.owner_profile_id else None,
            preferred_country=task.preferred_country.value if task.preferred_country else None,
            target_urls_json=json.dumps(target_urls),
            target_url=target_urls[0] if target_urls else None,
            original_url=task.original_url.url,
            explanation=task.explanation.content,
            status=task.status.value,
            version=task.version,
            run_version=task.run_version,
            attempt_id=str(task.attempt_id) if task.attempt_id else None,
            last_start_command_id=str(task.last_start_command_id) if task.last_start_command_id else None,
            retry_count=task.retry_count,
            max_retries=task.max_retries,
            proxy_id=str(task.proxy_id) if task.proxy_id else None,
            created_at=task.created_at,
            updated_at=task.updated_at,
            completed_at=task.completed_at,
            input_snapshot=task.input_snapshot,
            verification=task.verification,
            submitted_at=task.submitted_at,
            receipt_text=task.receipt_text,
            meta_case_number=task.meta_case_number,
            screenshot_path=task.screenshot_path,
            error_message=task.error_message,
            legacy_read_only=False,
        )
        self._session.add(model)
        await self._session.flush()

    async def save(self, task: ReportTask, *, expected_version: int, expected_attempt_id: Optional[UUID]) -> None:
        if self._operator_id is not None and task.operator_id != self._operator_id:
            raise StaleVersionError("Task owner does not match repository scope.")
        if task.version != expected_version + 1:
            raise StaleVersionError("A task mutation must advance exactly one version.")
        model = ReportTaskModel
        attempt = str(expected_attempt_id) if expected_attempt_id is not None else None
        values = {name: getattr(task, name) for name in (
            "version", "run_version", "retry_count", "meta_case_number", "screenshot_path",
            "error_message", "completed_at", "input_snapshot", "verification", "submitted_at",
            "receipt_text", "updated_at")}
        values.update(status=task.status.value,
                      attempt_id=str(task.attempt_id) if task.attempt_id else None,
                      last_start_command_id=str(task.last_start_command_id) if task.last_start_command_id else None,
                      proxy_id=str(task.proxy_id) if task.proxy_id else None)
        result = await self._session.execute(update(model).where(
            model.id == str(task.id), model.operator_account_id == str(task.operator_id),
            model.version == expected_version, model.attempt_id == attempt,
            model.legacy_read_only.is_(False), model.legacy_batch_job_id.is_(None),
        ).values(**values).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise StaleVersionError("Task version or attempt conflict.")
        await self._session.flush()
