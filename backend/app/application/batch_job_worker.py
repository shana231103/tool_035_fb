# File: backend/app/application/batch_job_worker.py
import asyncio
import logging
import random
from app.domain.entities.batch_job import BatchJob
from app.domain.entities.owner_profile import OwnerProfile
from app.domain.entities.report_task import ReportTask
from app.domain.exceptions.mailbox_errors import MailboxError
from app.domain.value_objects.enums import JobStatus, TaskStatus

logger = logging.getLogger(__name__)


class BatchJobWorker:
    """One shared executor, context budget and email lease registry per queue."""

    def __init__(self, uow_factory, executor, progress, verification, max_contexts,
                 email_slot_timeout, notifier):
        self._factory = uow_factory
        self._executor = executor
        self._progress = progress
        self._verification = verification
        self._notifier = notifier
        self._emails: dict[str, list] = {}
        self._capacity = asyncio.Semaphore(max_contexts)
        self._email_timeout = email_slot_timeout

    async def notify_job(self, job: BatchJob) -> None:
        try:
            await self._notifier.broadcast_job_update(str(job.id), {
                "status": job.status.value, "stats": job.calculate_stats()})
        except Exception:
            logger.warning("Job notification failed after persistence: %s", job.id)

    async def run(self, job: BatchJob, profile: OwnerProfile) -> None:
        try:
            while True:
                async with self._factory() as uow:
                    fresh = await uow.jobs.get_by_id(job.id)
                    if fresh.status != JobStatus.RUNNING:
                        return
                    queued = await uow.tasks.get_next_queued_tasks(job.id, job.concurrency)
                if not queued:
                    break
                results = await asyncio.gather(
                    *(self._process_single_item(t, job, profile) for t in queued),
                    return_exceptions=True)
                if any(isinstance(result, BaseException) for result in results):
                    raise RuntimeError("Worker state could not be persisted.")
                if await self._refresh_job(job.id) != JobStatus.RUNNING:
                    return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.error("Batch worker failed: %s", job.id)
            async with self._factory() as uow:
                fresh = await uow.jobs.get_by_id(job.id)
                if fresh.status != JobStatus.RUNNING:
                    return
                fresh.pause()
                await uow.jobs.save(fresh)
            await self.notify_job(fresh)
        else:
            await self._refresh_job(job.id)

    async def _refresh_job(self, job_id) -> JobStatus:
        async with self._factory() as uow:
            fresh = await uow.jobs.get_by_id(job_id)
            if fresh.status != JobStatus.RUNNING:
                return fresh.status
            fresh.update_completion_status()
            await uow.jobs.save(fresh)
        await self.notify_job(fresh)
        return fresh.status

    async def _process_single_item(self, task: ReportTask, job: BatchJob,
                                   profile: OwnerProfile) -> None:
        async with self._factory() as uow:
            profile = await uow.profiles.get_by_id(job.owner_profile_id)
        if not profile:
            task.mark_failed("Owner profile no longer exists.", False)
            await self._progress.save(task)
            return
        email = profile.email.value.strip().casefold()
        lease = self._emails.setdefault(email, [asyncio.Lock(), 0])
        lease[1] += 1
        acquired = False
        try:
            task.status = TaskStatus.WAITING_EMAIL_SLOT
            await self._progress.save(task)
            await asyncio.wait_for(lease[0].acquire(), self._email_timeout)
            acquired = True
            async with self._capacity:
                task.status = TaskStatus.QUEUED
                async with self._factory() as uow:
                    proxy = await uow.proxies.get_active_proxy(job.preferred_country)
                    profile = await uow.profiles.get_by_id(job.owner_profile_id)
                if not profile:
                    raise ValueError("Owner profile no longer exists.")
                if profile.email.value.strip().casefold() != email:
                    raise MailboxError("STALE")
                result = await self._executor.execute(task, profile, proxy)
                if proxy and (result.retryable or task.status == TaskStatus.SUBMITTED):
                    if result.retryable:
                        proxy.mark_failed()
                    else:
                        proxy.mark_active(proxy.latency_ms)
                    async with self._factory() as uow:
                        await uow.proxies.save(proxy)
            await asyncio.sleep(random.uniform(job.delay_min, job.delay_max))
        except asyncio.CancelledError:
            if task.status not in (TaskStatus.SUBMITTED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                task.cancel()
                task.verification = {}
                await self._progress.save(task)
            raise
        except Exception:
            task.mark_failed("Worker failed or email slot timed out before submission.", False)
            task.verification = {}
            await self._progress.save(task)
        finally:
            try:
                await self._verification.close(str(task.id))
            except Exception:
                logger.warning("Challenge cleanup failed: %s", task.id)
            finally:
                if acquired:
                    lease[0].release()
                lease[1] -= 1
                if not lease[1]:
                    self._emails.pop(email, None)

