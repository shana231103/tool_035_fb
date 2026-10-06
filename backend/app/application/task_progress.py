# File: backend/app/application/task_progress.py
import logging
from typing import Callable
from app.application.unit_of_work import IUnitOfWork
from app.application.job_serialization import task_to_dto
from app.application.dtos.verification_dtos import safe_verification_metadata
from app.domain.entities.report_task import ReportTask
from app.domain.ports.notifier import IEventNotifier

logger = logging.getLogger(__name__)


class ProgressStore:
    def __init__(self, factory: Callable[[], IUnitOfWork], notifier: IEventNotifier):
        self._factory = factory
        self._notifier = notifier

    async def save(self, task: ReportTask) -> None:
        await self.persist(task)
        await self.notify(task)

    async def persist(self, task: ReportTask) -> None:
        task.verification = safe_verification_metadata(task.verification)
        async with self._factory() as uow:
            await uow.tasks.save(task)

    async def notify(self, task: ReportTask) -> None:
        payload = task_to_dto(task).model_dump(mode="json")
        try:
            await self._notifier.broadcast_task_update(str(task.batch_job_id), str(task.id), payload)
        except Exception:
            logger.warning("Task notification failed after persistence: %s", task.id)
