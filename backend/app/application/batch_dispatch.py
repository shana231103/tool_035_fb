# File: backend/app/application/batch_dispatch.py
import asyncio
from dataclasses import replace

from app.application.bulk_import_review import profile_sha256, profile_submission_snapshot
from app.application.dispatch_claim import settle_owned
from app.domain.exceptions.mailbox_errors import MailboxError
from app.domain.value_objects.enums import JobStatus, TaskStatus


class BatchDispatch:
    def __init__(self, worker):
        self.worker = worker

    async def _wait_reason(self, task, reason):
        if task.waiting_reason != reason:
            async with self.worker._factory() as uow:
                await uow.tasks.save_wait_reason(task.id, task.dispatch_revision, reason)

    async def _fill(self, job_id, gate, active):
        worker, cursor = self.worker, None
        unavailable, busy, pending = False, False, False
        async with worker._factory() as uow:
            job = await uow.jobs.get_by_id(job_id)
            profile = await uow.profiles.get_by_id(job.owner_profile_id)
        if job.status != JobStatus.RUNNING or gate.closed:
            return job, "STOPPED"
        if any(t.status in (TaskStatus.SUBMITTING, TaskStatus.NEEDS_REVIEW) for t in job.tasks
               if t.id not in active):
            gate.close()
            return job, "SUBMISSION_REVIEW_REQUIRED"
        if (not profile or (job.bulk and
                profile_sha256(profile_submission_snapshot(profile)) != job.bulk.accepted_profile_sha256)):
            gate.close()
            return job, "PROFILE_REVIEW_REQUIRED"
        readiness = {}
        while len(active) < job.concurrency:
            async with worker._factory() as uow:
                page = await uow.tasks.list_dispatch_candidates(job_id, cursor, 100)
            for task in page.tasks:
                if task.id in active:
                    continue
                pending = True
                if job.bulk and not task.assignment:
                    raise ValueError("IMPORT_METADATA_INVALID")
                email = task.assignment.assigned_mail_email if job.bulk else profile.email.value.casefold()
                if worker.budget.email_busy(email):
                    busy = True
                    await self._wait_reason(task, "MAIL_BUSY")
                    continue
                if email not in readiness:
                    try:
                        binding = await worker.connections.resolve_binding(email)
                        await worker.connections.assert_ready(binding)
                        readiness[email] = True
                    except MailboxError:
                        readiness[email] = False
                if not readiness[email]:
                    unavailable = True
                    await self._wait_reason(task, "MAIL_UNAVAILABLE")
                    continue
                permit = worker.budget.try_acquire(task.id, email)
                if permit is None:
                    return job, "BUSY"
                child = asyncio.create_task(worker._execute_reserved(permit, job, gate))
                active[task.id] = child
                if len(active) >= job.concurrency:
                    break
            cursor = page.next_cursor
            if cursor is None or len(active) >= job.concurrency:
                break
        if busy:
            return job, "BUSY"
        if unavailable:
            return job, "MAIL_UNAVAILABLE"
        return job, "PENDING" if pending else "EMPTY"

    async def _pause(self, job_id, reason):
        async with self.worker._factory() as uow:
            job = await uow.jobs.get_by_id(job_id)
            if job.status == JobStatus.RUNNING:
                job.update_completion_status()
                job.pause()
                if job.bulk:
                    job.bulk = replace(job.bulk, pause_reason=reason, revision=job.bulk.revision + 1)
                await uow.jobs.save(job)
        await self.worker.notify_job(job)

    async def run(self, job_id, gate):
        active, reason, cancelled = {}, "EMPTY", False
        try:
            while True:
                revision = self.worker.budget.snapshot().revision
                job, reason = await self._fill(job_id, gate, active)
                if not active:
                    if reason in ("STOPPED", "EMPTY"):
                        break
                    if gate.closed or reason in ("MAIL_UNAVAILABLE", "PROFILE_REVIEW_REQUIRED",
                                                 "SUBMISSION_REVIEW_REQUIRED"):
                        await self._pause(job_id, reason)
                        break
                if gate.closed and active:
                    completed, _ = await asyncio.wait(tuple(active.values()),
                                                       return_when=asyncio.FIRST_COMPLETED)
                else:
                    waiter = asyncio.create_task(self.worker.budget.wait_changed(revision))
                    try:
                        completed, _ = await asyncio.wait((*active.values(), waiter),
                                                           return_when=asyncio.FIRST_COMPLETED)
                    finally:
                        waiter.cancel()
                        await asyncio.gather(waiter, return_exceptions=True)
                for task_id, child in tuple(active.items()):
                    if child.done():
                        active.pop(task_id)
                        if not child.cancelled():
                            outcome = child.result()
                            if outcome:
                                reason = outcome
                                gate.close()
                if not gate.closed:
                    await self.worker._refresh_job(job_id)
                elif not active:
                    await self._pause(job_id, reason)
                    break
        except asyncio.CancelledError:
            cancelled = True
            raise
        except Exception:
            reason = "EXECUTION_FAILED"
            gate.close()
        finally:
            gate.close()
            if cancelled:
                for child in active.values():
                    child.cancel()
            if active:
                async def join():
                    return await asyncio.gather(*active.values(), return_exceptions=True)
                await settle_owned(join())
            if not cancelled:
                if reason == "EMPTY":
                    await self.worker._refresh_job(job_id)
                elif reason not in ("STOPPED", "MAIL_UNAVAILABLE"):
                    await self._pause(job_id, reason)
