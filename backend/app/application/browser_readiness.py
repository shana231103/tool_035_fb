# File: backend/app/application/browser_readiness.py
from dataclasses import dataclass
from uuid import UUID

from app.domain.exceptions.domain_exceptions import EntityNotFoundError
from app.domain.ports.browser_sessions import IBrowserControl
from app.domain.value_objects.browser_status import (
    BrowserReadiness, TaskCleanupState, CleanupOutcome, ExternalCleanupConfirmation,
)


@dataclass(frozen=True)
class TaskBrowserStatusView:
    task_id: UUID
    cleanup_state: TaskCleanupState
    operation_refs: tuple[UUID, ...]
    can_retry: bool
    resource_allows_retry: bool
    retry_block_reason: str | None


@dataclass(frozen=True)
class BrowserStatusView:
    readiness: BrowserReadiness
    task: TaskBrowserStatusView | None = None


class BrowserReadinessUseCase:
    def __init__(self, control: IBrowserControl, uow_factory):
        self._control, self._factory = control, uow_factory

    async def execute(self, task_id: UUID | None = None) -> BrowserStatusView:
        status = await self._control.status(task_id)
        if task_id is None:
            return BrowserStatusView(status.readiness)
        async with self._factory() as uow:
            task = await uow.tasks.get_by_id(task_id)
            if task is None:
                raise EntityNotFoundError("Report task not found.")
        resource = status.task
        allows_retry = bool(resource and resource.resource_allows_retry)
        reason = resource.safe_reason if resource else "BROWSER_LEDGER_UNCERTAIN"
        if allows_retry and not task.can_retry_failed:
            reason = "TASK_NOT_ELIGIBLE"
        view = TaskBrowserStatusView(task_id,
            resource.cleanup_state if resource else TaskCleanupState.UNRESOLVED,
            resource.operation_refs if resource else (),
            task.can_retry_failed and allows_retry, allows_retry, reason)
        return BrowserStatusView(status.readiness, view)


class BrowserCleanupUseCase:
    def __init__(self, control: IBrowserControl):
        self._control = control

    async def retry(self, operation_id: UUID) -> CleanupOutcome:
        return await self._control.retry_cleanup(operation_id)

    async def confirm_external(self, confirmation: ExternalCleanupConfirmation) -> CleanupOutcome:
        return await self._control.confirm_external_cleanup(confirmation)
