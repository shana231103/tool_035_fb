# File: backend/app/application/use_cases/list_batch_jobs.py
from app.application.dtos.job_dtos import BatchJobPageResponseDTO
from app.application.job_serialization import job_to_dto


class ListBatchJobsUseCase:
    def __init__(self, uow_factory):
        self._uow_factory = uow_factory

    async def execute(self, limit=50, offset=0):
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("Invalid page bounds.")
        async with self._uow_factory() as uow:
            jobs = await uow.jobs.list_jobs(limit=limit + 1, offset=offset)
            return BatchJobPageResponseDTO(items=[job_to_dto(job) for job in jobs[:limit]],
                                           limit=limit, offset=offset, has_more=len(jobs) > limit)
