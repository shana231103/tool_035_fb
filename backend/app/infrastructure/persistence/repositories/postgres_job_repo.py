# File: backend/app/infrastructure/persistence/repositories/postgres_job_repo.py
from typing import List, Optional
from uuid import UUID
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.domain.entities.batch_job import BatchJob
from app.domain.ports.repositories import IBatchJobRepository
from app.infrastructure.persistence.mappers import DataMapper
from app.infrastructure.persistence.models import BatchJobModel, ReportTaskModel


class PostgresJobRepository(IBatchJobRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, job_id: UUID) -> Optional[BatchJob]:
        stmt = (
            select(BatchJobModel)
            .options(selectinload(BatchJobModel.tasks))
            .where(BatchJobModel.id == str(job_id))
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return DataMapper.job_to_domain(model) if model else None

    async def save(self, job: BatchJob) -> None:
        model = await self._session.get(BatchJobModel, str(job.id))
        if not model:
            model = DataMapper.job_to_model(job)
            self._session.add(model)
        else:
            model.name = job.name
            model.status = job.status.value
            model.preferred_country = job.preferred_country.value if job.preferred_country else None
            model.concurrency = job.concurrency
            model.delay_min = job.delay_min
            model.delay_max = job.delay_max
            model.completed_at = job.completed_at

        # Keep the loaded models alive for the whole upsert, avoiding one lookup
        # (and autoflush) per task when the session identity map is cold.
        task_models = {}
        if job.tasks:
            result = await self._session.execute(
                select(ReportTaskModel).where(
                    ReportTaskModel.batch_job_id == str(job.id)
                )
            )
            task_models = {task_model.id: task_model for task_model in result.scalars()}

        for task in job.tasks:
            task_id = str(task.id)
            task_model = task_models.get(task_id)
            if not task_model:
                task_model = DataMapper.task_to_model(task)
                self._session.add(task_model)
                task_models[task_id] = task_model
            else:
                task_model.status = task.status.value
                task_model.retry_count = task.retry_count
                task_model.proxy_id = str(task.proxy_id) if task.proxy_id else None
                task_model.meta_case_number = task.meta_case_number
                task_model.screenshot_path = task.screenshot_path
                task_model.error_message = task.error_message
                task_model.completed_at = task.completed_at

    async def list_jobs(self, limit: int = 50, offset: int = 0) -> List[BatchJob]:
        stmt = (
            select(BatchJobModel)
            .options(selectinload(BatchJobModel.tasks))
            .order_by(desc(BatchJobModel.created_at), desc(BatchJobModel.id))
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [DataMapper.job_to_domain(m) for m in models]

    async def delete(self, job_id: UUID) -> None:
        stmt = delete(BatchJobModel).where(BatchJobModel.id == str(job_id))
        await self._session.execute(stmt)
