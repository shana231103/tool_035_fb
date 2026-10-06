# File: backend/app/application/use_cases/process_batch_queue.py
import asyncio
from typing import Callable
from uuid import UUID
from app.application.unit_of_work import IUnitOfWork
from app.application.task_progress import ProgressStore
from app.application.batch_job_worker import BatchJobWorker
from app.application.mailbox_sessions import MailboxAttemptSessions
from app.domain.ports.mailbox_code_reader import IMailboxConnections
from app.domain.exceptions.mailbox_errors import MailboxError
from app.application.use_cases.execute_report_task import ExecuteReportTaskUseCase
from app.domain.exceptions.domain_exceptions import EntityNotFoundError
from app.domain.ports.automation_driver import IAutomationDriver
from app.domain.ports.notifier import IEventNotifier
from app.domain.ports.email_verification import IVerificationBroker
from app.domain.value_objects.enums import JobStatus, TaskStatus, PlatformType
from app.domain.value_objects.original_url import OriginalUrl
from app.domain.value_objects.target_url import TargetUrl


class ProcessBatchQueueUseCase:
    def __init__(self, uow_factory: Callable[[], IUnitOfWork], automation_driver: IAutomationDriver,
                 notifier: IEventNotifier, verification: IVerificationBroker,
                 max_contexts: int = 5, email_slot_timeout: float = 1800,
                 connections: IMailboxConnections | None = None,
                 sessions: MailboxAttemptSessions | None = None):
        self._factory = uow_factory
        self._connections = connections
        executor = ExecuteReportTaskUseCase(automation_driver, notifier, uow_factory,
                                           verification, connections, sessions)
        self._worker = BatchJobWorker(uow_factory, executor, ProgressStore(uow_factory, notifier),
                                      verification, max_contexts, email_slot_timeout, notifier)
        self._active_jobs: dict[UUID, asyncio.Task] = {}
        self._control = asyncio.Lock()
        self._closed = False
        self._shutdown_task: asyncio.Task | None = None

    async def start_job(self, job_id: UUID) -> None:
        async with self._control:
            if self._closed:
                raise ValueError("Queue is shutting down.")
            active = self._active_jobs.get(job_id)
            if active and not active.done():
                return
            async with self._factory() as uow:
                job = await uow.jobs.get_by_id(job_id)
                if not job:
                    raise EntityNotFoundError("Batch job not found.")
                profile = await uow.profiles.get_by_id(job.owner_profile_id)
                if not profile:
                    raise ValueError("Owner profile no longer exists.")
                profile.validate_for_submission()
                for task in job.tasks:
                    if TargetUrl.from_raw_url(task.target_url.url).platform != PlatformType.FACEBOOK:
                        raise ValueError("This workflow only runs Facebook Copyright jobs.")
                    OriginalUrl.from_raw_url(task.original_url.url)
                if any(t.status in (TaskStatus.SUBMITTING, TaskStatus.NEEDS_REVIEW) for t in job.tasks):
                    raise ValueError("Reconcile uncertain submissions before starting this job.")
                if not any(t.status in (TaskStatus.PENDING, TaskStatus.QUEUED) for t in job.tasks):
                    raise ValueError("No pending tasks remain. Use Retry failed tasks for eligible pre-submission failures.")
            if not self._connections:
                raise MailboxError("AUTH_REQUIRED")
            binding = await self._connections.resolve_binding(profile.email.value)
            await self._connections.assert_ready(binding)
            async with self._factory() as uow:
                job = await uow.jobs.get_by_id(job_id)
                job.start()
                job.completed_at = None
                await uow.jobs.save(job)
            worker = asyncio.create_task(self._worker.run(job, profile))
            self._active_jobs[job_id] = worker
            def release(finished):
                if self._active_jobs.get(job_id) is finished:
                    self._active_jobs.pop(job_id, None)
            worker.add_done_callback(release)
        await self._worker.notify_job(job)

    async def retry_failed_tasks(self, job_id: UUID) -> int:
        """Requeue safely in one transaction; explicit Start owns execution."""
        async with self._control:
            if self._closed:
                raise ValueError("Queue is shutting down.")
            active = self._active_jobs.get(job_id)
            if active and not active.done():
                raise ValueError("Wait for the active worker to finish before retrying.")
            async with self._factory() as uow:
                job = await uow.jobs.get_by_id(job_id)
                if not job:
                    raise EntityNotFoundError("Batch job not found.")
                in_flight = (TaskStatus.RUNNING, TaskStatus.WAITING_EMAIL_SLOT, TaskStatus.WAITING_EMAIL_CODE,
                             TaskStatus.VERIFYING_EMAIL, TaskStatus.SUBMITTING, TaskStatus.NEEDS_REVIEW)
                if job.status in (JobStatus.RUNNING, JobStatus.CANCELLED) or any(t.status in in_flight for t in job.tasks):
                    raise ValueError("Resolve active or uncertain submissions before retrying this job.")
                failed = [task for task in job.tasks if task.status == TaskStatus.FAILED]
                if any(task.has_submission_evidence for task in failed):
                    raise ValueError("Reconcile submission evidence on failed tasks before retrying this job.")
                eligible = [task for task in failed if task.can_retry_failed]
                if not eligible:
                    raise ValueError("No failed tasks remain within the retry limit.")
                for task in eligible:
                    task.retry_failed()
                    await uow.tasks.save(task)
                job.status, job.completed_at = JobStatus.PENDING, None
                await uow.jobs.save(job)
            return len(eligible)

    @staticmethod
    async def _finish_owned(task: asyncio.Task) -> None:
        """Delay repeated caller cancellation until owned cleanup has finished."""
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        result = task.result()
        if cancelled:
            raise asyncio.CancelledError
        return result

    async def stop_job(self, job_id: UUID) -> None:
        await self._finish_owned(asyncio.create_task(self._stop_job(job_id)))

    async def _stop_job(self, job_id: UUID) -> None:
        async with self._control:
            async with self._factory() as uow:
                initial = await uow.jobs.get_by_id(job_id)
                if not initial:
                    raise EntityNotFoundError("Batch job not found.")
            running = self._active_jobs.get(job_id)
            if running:
                if not running.done():
                    running.cancel()
                await asyncio.gather(running, return_exceptions=True)
            if self._active_jobs.get(job_id) is running:
                self._active_jobs.pop(job_id, None)
            if initial.is_terminal or initial.status == JobStatus.PAUSED:
                return
            async with self._factory() as uow:
                job = await uow.jobs.get_by_id(job_id)
                if not job:
                    raise EntityNotFoundError("Batch job not found.")
                if job.is_terminal or job.status == JobStatus.PAUSED:
                    return
                job.update_completion_status()
                job.pause()
                await uow.jobs.save(job)
        await self._worker.notify_job(job)

    async def shutdown(self) -> None:
        self._closed = True
        if self._shutdown_task is None:
            self._shutdown_task = asyncio.create_task(self._shutdown())
        await self._finish_owned(self._shutdown_task)

    async def _shutdown(self) -> None:
        # Wait for an admitted Start to publish its handle before taking ownership.
        async with self._control:
            job_ids = list(self._active_jobs)
        for job_id in job_ids:
            await self._stop_job(job_id)
        # A worker can still be cleaning up after a terminal/paused state was saved.
        remaining = list(self._active_jobs.values())
        for running in remaining:
            if not running.done():
                running.cancel()
        await asyncio.gather(*remaining, return_exceptions=True)
        self._active_jobs.clear()
