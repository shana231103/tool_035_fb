# File: backend/app/application/use_cases/list_report_tasks.py
"""Use case for listing and retrieving standalone report tasks via read-only queries."""

from typing import Optional
from uuid import UUID

from app.application.task_records import TaskPage, TaskView
from app.application.unit_of_work import IUnitOfWorkFactory


class ListReportTasksUseCase:
    def __init__(self, uow_factory: IUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(
        self,
        owner: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> TaskPage:
        async with self._uow_factory.operator(owner) as uow:
            if not uow.task_queries:
                return TaskPage(items=(), limit=limit, offset=offset, has_more=False)
            # Query limit + 1 to determine has_more
            records = await uow.task_queries.list_tasks(
                limit=limit + 1,
                offset=offset,
            )
            has_more = len(records) > limit
            items = records[:limit]
            return TaskPage(
                items=items,
                limit=limit,
                offset=offset,
                has_more=has_more,
            )

    async def detail(
        self,
        owner: UUID,
        task_id: UUID,
    ) -> Optional[TaskView]:
        async with self._uow_factory.operator(owner) as uow:
            if not uow.task_queries:
                return None
            m = await uow.task_queries.get_detail(task_id)
            if not m:
                return None
            return TaskView(
                id=m.id,
                operator_id=m.operator_id,
                name=m.name,
                status=m.status,
                version=m.version,
                target_urls=m.target_urls,
                target_count=m.target_count,
                original_url=m.original_url or "",
                explanation=m.explanation or "",
                owner_profile_id=m.owner_profile_id or UUID("00000000-0000-0000-0000-000000000000"),
                preferred_country=m.preferred_country,
                retry_count=m.retry_count,
                max_retries=m.max_retries,
                created_at=m.created_at,
                updated_at=m.updated_at,
                attempt_id=m.attempt_id,
                completed_at=m.completed_at,
                meta_case_number=m.meta_case_number,
                receipt_text=m.receipt_text,
                screenshot_path=m.screenshot_path,
                error_message=m.error_message,
                safe_error_code=m.safe_error_code,
                submitted_at=m.submitted_at,
                can_retry=m.can_retry,
                has_submission_evidence=m.has_submission_evidence,
                legacy_read_only=m.legacy_read_only,
            )
