# File: backend/app/application/browser_receipts.py
"""Receipt-first persistence independent of revoked initiating sessions."""
import asyncio
from dataclasses import fields
from app.application.owned_tasks import current_ownership
from app.application.task_runtime_records import OwnedWorkKind

from app.domain.entities.report_task import ReportTask
from app.domain.value_objects.enums import TaskStatus


class ReceiptPersistenceError(ValueError):
    def __init__(self):
        super().__init__("BROWSER_RECEIPT_PERSISTENCE_UNCERTAIN")


async def finish_owned(operation, kind=OwnedWorkKind.RECEIPT):
    """Keep a strong finite owner and propagate caller cancellation after settlement."""
    owner = asyncio.create_task(operation)
    ownership = current_ownership.get()
    if ownership:
        registry, parent, attempt_id = ownership
        try:
            registry.register(kind, owner, attempt_id=attempt_id, parent=parent)
        except RuntimeError:
            owner.cancel()
            await asyncio.gather(owner, return_exceptions=True)
            raise
    cancelled = False
    while not owner.done():
        try:
            await asyncio.shield(owner)
        except asyncio.CancelledError:
            cancelled = True
    result = owner.result()
    if cancelled:
        raise asyncio.CancelledError
    return result


def copy_task_state(target: ReportTask, source: ReportTask):
    for item in fields(ReportTask):
        setattr(target, item.name, getattr(source, item.name))


def matching_task(task, grant):
    return (task is not None and task.operator_id == grant.scope.operator_id
            and task.id == grant.scope.task_id and task.attempt_id == grant.attempt_id
            and task.run_version == grant.run_version and task.last_start_command_id == grant.command_id)


def matching_receipt(task, grant, receipt):
    return (matching_task(task, grant) and task.status == TaskStatus.SUBMITTED
            and task.receipt_text == receipt.receipt_text and task.meta_case_number == receipt.case_number)


class BrowserReceiptPersister:
    def __init__(self, factory):
        self._factory = factory

    async def persist(self, grant, receipt):
        return await finish_owned(self._persist(grant, receipt))

    async def _persist(self, grant, receipt):
        if receipt.task_id != grant.scope.task_id or receipt.attempt_id != grant.attempt_id:
            raise ReceiptPersistenceError()
        try:
            async with self._factory.execution(grant) as uow:
                fresh = await uow.tasks.get_by_id(receipt.task_id)
                if not matching_task(fresh, grant) or fresh.status not in (
                        TaskStatus.SUBMITTING, TaskStatus.NEEDS_REVIEW, TaskStatus.SUBMITTED):
                    raise ReceiptPersistenceError()
                if fresh.receipt_text and not matching_receipt(fresh, grant, receipt):
                    raise ReceiptPersistenceError()
                if matching_receipt(fresh, grant, receipt):
                    return fresh
                version = fresh.version
                fresh.mark_submitted(receipt_text=receipt.receipt_text,
                                     case_number=receipt.case_number, screenshot_path=fresh.screenshot_path)
                fresh.completed_at = receipt.observed_at
                fresh.verification = {}
                await uow.tasks.save(fresh, expected_version=version, expected_attempt_id=grant.attempt_id)
                await uow.commit()
                return fresh
        except Exception:
            try:
                async with self._factory.owned(grant.scope.operator_id) as uow:
                    fresh = await uow.tasks.get_by_id(receipt.task_id)
                    if matching_receipt(fresh, grant, receipt):
                        return fresh
            except Exception:
                raise ReceiptPersistenceError() from None
            raise ReceiptPersistenceError() from None
