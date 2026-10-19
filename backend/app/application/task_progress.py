# File: backend/app/application/task_progress.py
"""Fresh aggregate progress, persisted before owner-scoped invalidation."""
import logging

from app.domain.value_objects.enums import TaskStatus


class ProgressStore:
    def __init__(self, factory, notifier, authority):
        self._factory, self._notifier, self._authority = factory, notifier, authority

    async def persist(self, grant, status, metadata):
        async with self._factory.execution(grant) as uow:
            if status == TaskStatus.SUBMITTING:
                task = await self._authority.match_grant(uow, grant)
                if task.status != TaskStatus.SUBMITTING:
                    raise ValueError("EXECUTION_GRANT_MISMATCH")
            else:
                task = await self._authority.require_run(uow, grant)
                version = task.version
                task.mark_progress(status, {"stage": metadata.stage,
                    "completed": metadata.completed, "total": metadata.total})
                await uow.tasks.save(task, expected_version=version, expected_attempt_id=grant.attempt_id)
                await uow.commit()
        await self.notify(task)
        return task

    async def notify(self, task):
        try:
            await self._notifier.broadcast_standalone_task_update(
                str(task.id), task.version, task.attempt_id,
                {"status": task.status.value}, owner_id=task.operator_id)
        except Exception:
            logging.getLogger(__name__).warning("TASK_NOTIFICATION_FAILED")
