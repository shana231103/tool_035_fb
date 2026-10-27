# File: backend/app/application/batch_start.py
from datetime import datetime, timezone
from app.application.bulk_import_models import BulkImportError
from app.domain.exceptions.domain_exceptions import EntityNotFoundError
from app.domain.exceptions.mailbox_errors import MailboxError
from app.domain.value_objects.bulk_import import AcceptedBulkReview
from app.domain.value_objects.enums import PlatformType, TaskStatus
from app.domain.value_objects.original_url import OriginalUrl
from app.domain.value_objects.target_url import TargetUrl


async def prepare_job_start(queue, job_id, review_sha256):
    async with queue._factory() as uow:
        job = await uow.jobs.get_by_id(job_id)
        if not job:
            raise EntityNotFoundError("Batch job not found.")
        profile = await uow.profiles.get_by_id(job.owner_profile_id)
        if not profile:
            raise ValueError("Owner profile no longer exists.")
        profile.validate_for_submission()
        for task in job.tasks:
            if TargetUrl.from_raw_url(task.target_url.url).platform != PlatformType.FACEBOOK:
                raise ValueError("Only Facebook Copyright jobs may run.")
            OriginalUrl.from_raw_url(task.original_url.url)
        if any(t.status in (TaskStatus.SUBMITTING, TaskStatus.NEEDS_REVIEW) for t in job.tasks):
            raise ValueError("Reconcile uncertain submissions before starting this job.")
        if not any(t.status in (TaskStatus.PENDING, TaskStatus.QUEUED) for t in job.tasks):
            raise ValueError("No pending tasks remain. Use Retry failed tasks for eligible failures.")
    if not queue._connections:
        raise MailboxError("AUTH_REQUIRED")
    if queue._browser:
        status = await queue._browser.status()
        if status.readiness.safe_reason != "BROWSER_CAPACITY_WAIT":
            await queue._browser.assert_ready()
    if job.bulk:
        review, snapshot = await queue._bulk_review.review_with_profile(job_id)
        if not review.can_start or review.review_sha256 != review_sha256:
            raise BulkImportError("STALE_REVIEW", status_code=409)
        accepted = AcceptedBulkReview(review.review_sha256, review.profile_sha256, snapshot,
                                      datetime.now(timezone.utc), job.bulk.accepted_profile_sha256)
        if queue._closed:
            raise ValueError("Queue is shutting down.")
        async with queue._factory() as uow:
            if not await uow.bulk_imports.accept_start(job_id, review.bulk_revision,
                                                     job.status, accepted):
                raise BulkImportError("STALE_REVIEW", status_code=409)
        async with queue._factory() as uow:
            job = await uow.jobs.get_by_id(job_id)
    else:
        if queue._browser:
            for task in job.tasks:
                if task.status in (TaskStatus.PENDING, TaskStatus.QUEUED):
                    await queue._browser.assert_task_retriable(task.id)
        binding = await queue._connections.resolve_binding(profile.email.value)
        await queue._connections.assert_ready(binding)
        if queue._closed:
            raise ValueError("Queue is shutting down.")
        async with queue._factory() as uow:
            job = await uow.jobs.get_by_id(job_id)
            if any(t.has_submission_evidence or t.status in (TaskStatus.SUBMITTING, TaskStatus.NEEDS_REVIEW)
                   for t in job.tasks if t.status in (TaskStatus.PENDING, TaskStatus.QUEUED,
                                                     TaskStatus.SUBMITTING, TaskStatus.NEEDS_REVIEW)):
                raise ValueError("Task state changed before Start.")
            job.start()
            job.completed_at = None
            for task in job.tasks:
                if task.status == TaskStatus.QUEUED:
                    await uow.tasks.save(task)
            await uow.jobs.save(job)
    return job, profile
