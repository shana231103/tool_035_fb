# File: backend/app/application/bulk_import_review.py
from dataclasses import asdict
from app.application.bulk_import_canonical import binding_value, digest
from app.application.bulk_import_models import BulkImportError, BulkStartReview
from app.domain.exceptions.mailbox_errors import MailboxError
from app.domain.value_objects.bulk_import import ProfileSubmissionSnapshot
from app.domain.value_objects.enums import JobStatus, TaskStatus
from app.domain.value_objects.mailbox_verification import normalize_email


def profile_submission_snapshot(profile):
    profile.validate_for_submission()
    return ProfileSubmissionSnapshot(profile.id, profile.rights_owner_name, profile.sender_name,
                                     profile.rights_jurisdiction, profile.owner_role)


def profile_sha256(snapshot):
    return digest({"version": "bulk-profile-v1", **asdict(snapshot)})


class BulkReviewService:
    def __init__(self, uow_factory, connections):
        self._uow_factory, self._connections = uow_factory, connections

    async def review_job(self, job_id):
        review, _ = await self.review_with_profile(job_id)
        return review

    async def review_with_profile(self, job_id):
        async with self._uow_factory() as uow:
            job = await uow.jobs.get_by_id(job_id)
            if job is None:
                raise BulkImportError("IMPORT_NOT_FOUND", status_code=404)
            if job.bulk is None:
                raise BulkImportError("IMPORT_METADATA_INVALID")
            profile = await uow.profiles.get_by_id(job.owner_profile_id)
            if profile is None:
                raise BulkImportError("PROFILE_REVIEW_REQUIRED", status_code=409)
            try:
                snapshot = profile_submission_snapshot(profile)
            except ValueError:
                raise BulkImportError("PROFILE_REVIEW_REQUIRED", status_code=409) from None
        pending = [task for task in job.tasks if task.status in (TaskStatus.PENDING, TaskStatus.QUEUED)]
        if any(task.assignment is None for task in pending):
            raise BulkImportError("IMPORT_METADATA_INVALID")
        pending_values = []
        for task in sorted(pending, key=lambda task: task.assignment.sequence):
            if task.assignment is None:
                raise BulkImportError("IMPORT_METADATA_INVALID")
            pending_values.append({"id": task.id, "status": task.status,
                "revision": task.dispatch_revision, "assignment": asdict(task.assignment),
                "original": task.original_url.url, "targets": task.target_url.url,
                "explanation": task.explanation.content, "evidence": task.has_submission_evidence})
        pending_digest = digest({"version": "bulk-pending-v1", "tasks": pending_values})
        readiness, unavailable, runnable = [], 0, 0
        needed = {task.assignment.assigned_mail_email for task in pending}
        for email in job.bulk.ordered_mail_pool:
            if email not in needed:
                continue
            try:
                binding = await self._connections.resolve_binding(email)
                await self._connections.assert_ready(binding)
                if normalize_email(binding.meta_email) != email:
                    raise MailboxError("MAPPING_INVALID")
                readiness.append(binding_value(binding))
                runnable += sum(task.assignment.assigned_mail_email == email for task in pending)
            except MailboxError:
                readiness.append({"email": email, "reason": "MAIL_UNAVAILABLE"})
                unavailable += sum(task.assignment.assigned_mail_email == email for task in pending)
        blocked = []
        if any(task.status in (TaskStatus.NEEDS_REVIEW, TaskStatus.SUBMITTING) for task in job.tasks):
            blocked.append("PROFILE_REVIEW_REQUIRED")
        if job.status not in (JobStatus.PENDING, JobStatus.PAUSED, JobStatus.RUNNING):
            blocked.append("IMPORT_METADATA_INVALID")
        if not runnable:
            blocked.append("MAIL_UNAVAILABLE" if pending else "NO_PENDING_TASKS")
        profile_hash = profile_sha256(snapshot)
        mail_hash = digest({"version": "bulk-mail-readiness-v1", "bindings": readiness})
        review_hash = digest({"version": "bulk-start-review-v1", "job_id": job.id,
            "import_id": job.bulk.import_id, "revision": job.bulk.revision, "status": job.status,
            "pending": pending_digest, "profile": profile_hash, "mail": mail_hash})
        return BulkStartReview(job.id, job.bulk.revision, job.status.value, profile_hash,
            pending_digest, mail_hash, review_hash, {"MAIL_UNAVAILABLE": unavailable},
            tuple(blocked), not blocked, snapshot), snapshot
