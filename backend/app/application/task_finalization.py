# File: backend/app/application/task_finalization.py
"""Fresh exact-attempt finalization; confirmed receipt always wins."""
from app.application.browser_receipts import finish_owned, matching_task
from app.application.task_runtime_records import OwnedWorkKind
from app.domain.value_objects.enums import TaskStatus


class TaskFinalizer:
    def __init__(self, factory, progress=None):
        self._factory, self._progress = factory, progress

    async def begin_attempt(self, grant, prepared):
        async with self._factory.execution(grant) as uow:
            task = await uow.tasks.get_by_id(grant.scope.task_id)
            if not matching_task(task, grant) or task.status != TaskStatus.PREPARING or prepared.grant != grant:
                raise ValueError("EXECUTION_GRANT_MISMATCH")
            version = task.version
            task.input_snapshot = prepared.snapshot()
            task.mark_running(proxy_id=prepared.proxy_id)
            await uow.tasks.save(task, expected_version=version, expected_attempt_id=grant.attempt_id)
            await uow.commit()
        if self._progress:
            await self._progress.notify(task)
        return task

    async def finalize(self, grant, outcome):
        return await finish_owned(self._finalize(grant, outcome), OwnedWorkKind.FINALIZER)

    async def _finalize(self, grant, outcome):
        async with self._factory.execution(grant) as uow:
            task = await uow.tasks.get_by_id(grant.scope.task_id)
            if not matching_task(task, grant):
                raise ValueError("EXECUTION_GRANT_MISMATCH")
            version = task.version
            if task.status == TaskStatus.SUBMITTED:
                if outcome.screenshot_path and task.screenshot_path != outcome.screenshot_path:
                    task.screenshot_path = outcome.screenshot_path
                    task.version += 1
                else:
                    return task
            elif outcome.status == TaskStatus.CANCELLED:
                task.cancel()
            else:
                task.mark_failed(outcome.safe_code or "EXECUTION_INTERRUPTED", retryable=False)
            task.verification = {}
            await uow.tasks.save(task, expected_version=version, expected_attempt_id=grant.attempt_id)
            await uow.commit()
        if self._progress:
            await self._progress.notify(task)
        return task
