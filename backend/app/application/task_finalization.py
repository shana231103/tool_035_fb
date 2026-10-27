# File: backend/app/application/task_finalization.py
from app.application.browser_receipts import copy_task_state, finish_owned
from app.domain.entities.report_task import ReportTask
from app.domain.value_objects.enums import TaskStatus


class TaskFinalizer:
    """Persist terminal candidates only against their fresh, matching attempt."""

    def __init__(self, uow_factory, progress=None):
        self._factory, self._progress = uow_factory, progress

    async def finalize(self, candidate: ReportTask) -> bool:
        return await finish_owned(self._finalize(candidate))

    async def persist_terminal(self, candidate: ReportTask) -> ReportTask:
        await self.finalize(candidate)
        return candidate

    async def begin_attempt(self, candidate: ReportTask, previous_attempt: str | None,
                            *, claim=None) -> bool:
        if claim is not None:
            return await finish_owned(self._claim(candidate, claim))
        await finish_owned(self._begin_attempt(candidate, previous_attempt))
        return True

    async def _claim(self, candidate, claim) -> bool:
        try:
            async with self._factory() as uow:
                applied = await uow.tasks.claim_attempt(claim)
        except Exception:
            async with self._factory() as uow:
                current = await uow.tasks.get_by_id(claim.task_id)
            if (current is not None and current.attempt_id == claim.new_attempt_id
                    and current.dispatch_revision == claim.expected_dispatch_revision + 1):
                copy_task_state(candidate, current)
                return True
            if (current is not None and current.attempt_id == claim.expected_previous_attempt_id
                    and current.dispatch_revision == claim.expected_dispatch_revision
                    and current.status == TaskStatus.QUEUED and not current.has_submission_evidence):
                return False
            raise ValueError("ADMISSION_OUTCOME_UNKNOWN") from None
        if applied:
            candidate.dispatch_revision = claim.expected_dispatch_revision + 1
            if self._progress is not None:
                await self._progress.notify(candidate)
        return applied

    async def _begin_attempt(self, candidate: ReportTask, previous_attempt: str | None) -> None:
        async with self._factory() as uow:
            fresh = await uow.tasks.get_by_id(candidate.id)
            if (fresh is None or fresh.attempt_id != previous_attempt or fresh.has_submission_evidence
                    or fresh.status not in (TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.RUNNING,
                                            TaskStatus.WAITING_EMAIL_SLOT)):
                raise ValueError("Task attempt changed or submission requires reconciliation.")
            candidate.dispatch_revision = fresh.dispatch_revision + 1
            await uow.tasks.save(candidate)
        if self._progress is not None:
            await self._progress.notify(candidate)

    async def _finalize(self, candidate: ReportTask) -> bool:
        async with self._factory() as uow:
            fresh = await uow.tasks.get_by_id(candidate.id)
            if (fresh is None or fresh.attempt_id != candidate.attempt_id
                    or fresh.dispatch_revision != candidate.dispatch_revision):
                return False
            if fresh.status == TaskStatus.SUBMITTED:
                if candidate.screenshot_path and candidate.receipt_text == fresh.receipt_text:
                    fresh.screenshot_path = candidate.screenshot_path
                fresh.verification = {}
                await uow.tasks.save(fresh)
                committed = fresh
            else:
                if fresh.status in (TaskStatus.SUBMITTING, TaskStatus.NEEDS_REVIEW) and candidate.status not in (
                        TaskStatus.SUBMITTED, TaskStatus.NEEDS_REVIEW):
                    candidate.status = TaskStatus.NEEDS_REVIEW
                await uow.tasks.save(candidate)
                committed = candidate
        copy_task_state(candidate, committed)
        if self._progress is not None:
            await self._progress.notify(candidate)
        return True
