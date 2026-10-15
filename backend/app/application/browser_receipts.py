# File: backend/app/application/browser_receipts.py
import asyncio
from dataclasses import fields

from app.domain.entities.report_task import ReportTask
from app.domain.ports.automation_driver import AutomationReceipt
from app.domain.value_objects.enums import TaskStatus


class ReceiptPersistenceError(ValueError):
    def __init__(self):
        super().__init__("BROWSER_RECEIPT_PERSISTENCE_UNCERTAIN")


async def finish_owned(operation):
    """Drain a finite owned operation despite repeated caller cancellation."""
    owner = asyncio.create_task(operation)
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


def copy_task_state(target: ReportTask, source: ReportTask) -> None:
    for item in fields(ReportTask):
        setattr(target, item.name, getattr(source, item.name))


class BrowserReceiptPersister:
    def __init__(self, uow_factory):
        self._factory = uow_factory

    async def persist(self, task: ReportTask, receipt: AutomationReceipt) -> None:
        await finish_owned(self._persist(task, receipt))

    async def commit_receipt(self, receipt: AutomationReceipt) -> None:
        await finish_owned(self._persist(None, receipt))

    async def _persist(self, task: ReportTask | None, receipt: AutomationReceipt) -> None:
        if task is not None and (receipt.task_id != task.id or str(receipt.attempt_id) != task.attempt_id):
            raise ReceiptPersistenceError()
        try:
            async with self._factory() as uow:
                fresh = await uow.tasks.get_by_id(receipt.task_id)
                if fresh is None or fresh.attempt_id != str(receipt.attempt_id) or fresh.status not in (
                        TaskStatus.SUBMITTING, TaskStatus.NEEDS_REVIEW, TaskStatus.SUBMITTED):
                    raise ReceiptPersistenceError()
                if fresh.receipt_text is not None and (
                        fresh.receipt_text != receipt.receipt_text
                        or fresh.meta_case_number != receipt.case_number):
                    raise ReceiptPersistenceError()
                if fresh.status == TaskStatus.SUBMITTED and fresh.receipt_text == receipt.receipt_text:
                    committed = fresh
                else:
                    completed_at = fresh.completed_at
                    fresh.mark_submitted(receipt.case_number, fresh.screenshot_path)
                    fresh.completed_at = completed_at or receipt.observed_at
                    fresh.submitted_at = fresh.submitted_at or receipt.observed_at
                    fresh.receipt_text = receipt.receipt_text
                    fresh.verification = {}
                    await uow.tasks.save(fresh)
                    committed = fresh
            if task is not None:
                copy_task_state(task, committed)
        except Exception:
            try:
                async with self._factory() as uow:
                    fresh = await uow.tasks.get_by_id(receipt.task_id)
                    confirmed = (fresh is not None and fresh.attempt_id == str(receipt.attempt_id)
                                 and fresh.status == TaskStatus.SUBMITTED
                                 and fresh.receipt_text == receipt.receipt_text
                                 and fresh.meta_case_number == receipt.case_number)
                if confirmed:
                    if task is not None:
                        copy_task_state(task, fresh)
                    return
            except Exception:
                confirmed = False
            raise ReceiptPersistenceError() from None
