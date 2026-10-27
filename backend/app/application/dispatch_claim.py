# File: backend/app/application/dispatch_claim.py
import asyncio
from app.application.execution_context import AdmissionOutcomeUnknown
from app.domain.value_objects.bulk_import import UnstartedClaimRestore


async def settle_owned(operation):
    owner = asyncio.create_task(operation)
    cancelled = False
    while not owner.done():
        try:
            await asyncio.shield(owner)
        except asyncio.CancelledError:
            cancelled = True
    return owner.result(), cancelled


async def restore_unstarted(factory, claim) -> None:
    try:
        async with factory() as uow:
            restored = await uow.tasks.restore_unstarted(UnstartedClaimRestore(claim, True, True))
    except Exception:
        restored = False
    if restored:
        return
    async with factory() as uow:
        current = await uow.tasks.get_by_id(claim.task_id)
    if (current and current.attempt_id == claim.expected_previous_attempt_id
            and current.dispatch_revision == claim.expected_dispatch_revision + 2
            and current.status.value == "QUEUED" and not current.has_submission_evidence):
        return
    raise AdmissionOutcomeUnknown(claim.task_id, claim.new_attempt_id)
