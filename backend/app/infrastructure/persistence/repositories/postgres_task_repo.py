# File: backend/app/infrastructure/persistence/repositories/postgres_task_repo.py
from typing import List, Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.entities.report_task import ReportTask
from app.domain.ports.repositories import IReportTaskRepository
from app.domain.value_objects.enums import TaskStatus
from app.infrastructure.persistence.mappers import DataMapper
from app.infrastructure.persistence.models import ReportTaskModel


class PostgresTaskRepository(IReportTaskRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, task_id: UUID) -> Optional[ReportTask]:
        model = await self._session.get(ReportTaskModel, str(task_id))
        return DataMapper.task_to_domain(model) if model else None

    async def save(self, task: ReportTask) -> None:
        model = await self._session.get(ReportTaskModel, str(task.id))
        if not model:
            self._session.add(DataMapper.task_to_model(task))
        else:
            model.status = task.status.value
            model.retry_count = task.retry_count
            model.proxy_id = str(task.proxy_id) if task.proxy_id else None
            model.meta_case_number = task.meta_case_number
            model.screenshot_path = task.screenshot_path
            model.error_message = task.error_message
            model.infringing_account = task.infringing_account
            model.completed_at = task.completed_at
            model.attempt_id = task.attempt_id
            model.input_snapshot = task.input_snapshot
            model.verification = task.verification
            model.submitted_at = task.submitted_at
            model.receipt_text = task.receipt_text

    async def get_next_queued_tasks(self, job_id: UUID, limit: int = 10) -> List[ReportTask]:
        stmt = (
            select(ReportTaskModel)
            .where(
                ReportTaskModel.batch_job_id == str(job_id),
                ReportTaskModel.status.in_([TaskStatus.QUEUED.value, TaskStatus.PENDING.value]),
            )
            .order_by(ReportTaskModel.created_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [DataMapper.task_to_domain(m) for m in models]

    async def list_tasks_by_job(self, job_id: UUID) -> List[ReportTask]:
        stmt = (
            select(ReportTaskModel)
            .where(ReportTaskModel.batch_job_id == str(job_id))
            .order_by(ReportTaskModel.created_at)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [DataMapper.task_to_domain(m) for m in models]
