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
from app.infrastructure.persistence.bulk_import_mapping import validate_job_assignments


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
            validate_job_assignments(job)
            model = DataMapper.job_to_model(job)
            self._session.add(model)
            self._session.add_all([DataMapper.task_to_model(task) for task in job.tasks])
        else:
            model.name = job.name
            model.status = job.status.value
            model.preferred_country = job.preferred_country.value if job.preferred_country else None
            model.concurrency = job.concurrency
            model.delay_min = job.delay_min
            model.delay_max = job.delay_max
            model.completed_at = job.completed_at
        # Existing aggregate saves are state-only. Tasks have their own fresh-attempt authority.

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
