# File: backend/app/infrastructure/persistence/repositories/bulk_import_repo.py
from dataclasses import replace
from uuid import UUID
from sqlalchemy import exists, select, update
from sqlalchemy.orm import selectinload
from app.domain.value_objects.bulk_import import BulkReviewAcceptance, ImportMatch
from app.domain.value_objects.enums import JobStatus, TaskStatus
from app.infrastructure.persistence.bulk_import_mapping import bulk_from_model, bulk_to_fields, validate_job_assignments
from app.infrastructure.persistence.mappers import DataMapper
from app.infrastructure.persistence.models import BatchJobModel as Job, ReportTaskModel as Task, OwnerProfileModel as Profile


def profile_matches(snapshot, email=None):
    conditions = [Profile.id == str(snapshot.profile_id), Profile.rights_owner_name == snapshot.owner_name,
        Profile.sender_name == snapshot.sender_name, Profile.rights_jurisdiction == snapshot.rights_jurisdiction,
        Profile.owner_role == snapshot.owner_role.value, Profile.owner_role == "OWNER"]
    if email is not None:
        conditions.append(Profile.email == email)
    return exists(select(Profile.id).where(*conditions))


def no_evidence():
    return [Task.submitted_at.is_(None), Task.receipt_text.is_(None),
            Task.meta_case_number.is_(None), Task.screenshot_path.is_(None)]


class BulkImportRepository:
    def __init__(self, session):
        self._session = session

    async def get_by_import_id(self, import_id: UUID):
        result = await self._session.execute(select(Job).options(selectinload(Job.tasks))
            .where(Job.bulk_import_id == str(import_id)))
        model = result.scalar_one_or_none()
        return DataMapper.job_to_domain(model) if model else None

    async def find_content_matches(self, content_sha256: str, limit: int = 20):
        result = await self._session.execute(select(Job).options(selectinload(Job.tasks))
            .where(Job.bulk_content_sha256 == content_sha256)
            .order_by(Job.created_at.desc(), Job.id.desc()).limit(min(max(limit, 1), 20)))
        matches = []
        for model in result.scalars():
            job = DataMapper.job_to_domain(model)
            matches.append(ImportMatch(job.id, job.bulk.import_id, job.status, job.bulk.revision,
                sum(task.status == TaskStatus.SUBMITTED for task in job.tasks),
                any(task.status in (TaskStatus.SUBMITTING, TaskStatus.NEEDS_REVIEW) for task in job.tasks)))
        return tuple(matches)

    async def insert_draft(self, job):
        validate_job_assignments(job)
        if job.bulk is None or job.status != JobStatus.PENDING or any(
                task.status != TaskStatus.PENDING or task.has_submission_evidence or task.attempt_id
                or task.dispatch_revision != 0 or task.batch_job_id != job.id for task in job.tasks):
            raise ValueError("IMPORT_METADATA_INVALID")
        self._session.add(DataMapper.job_to_model(job))
        self._session.add_all([DataMapper.task_to_model(task) for task in job.tasks])
        await self._session.flush()

    async def accept_start(self, job_id, expected_revision, expected_status, review):
        model = await self._session.get(Job, str(job_id))
        if model is None or model.bulk_revision != expected_revision or model.status != expected_status.value:
            return False
        bulk = bulk_from_model(model)
        if bulk is None or bulk.accepted_profile_sha256 != review.previous_profile_sha256:
            return False
        acceptance = BulkReviewAcceptance(review.previous_profile_sha256, review.profile_sha256,
                                          review.review_sha256, review.accepted_at)
        updated = replace(bulk, revision=bulk.revision + 1, accepted_profile_sha256=review.profile_sha256,
                          last_acceptance=acceptance, pause_reason=None)
        blocked = exists(select(Task.id).where(Task.batch_job_id == str(job_id),
            Task.status.in_([TaskStatus.SUBMITTING.value, TaskStatus.NEEDS_REVIEW.value])))
        eligible = exists(select(Task.id).where(Task.batch_job_id == str(job_id),
            Task.status.in_([TaskStatus.PENDING.value, TaskStatus.QUEUED.value]), *no_evidence()))
        result = await self._session.execute(update(Job).where(Job.id == str(job_id),
            Job.bulk_revision == expected_revision, Job.status == expected_status.value,
            Job.owner_profile_id == str(review.profile.profile_id),
            Job.bulk_profile_sha256 == review.previous_profile_sha256,
            profile_matches(review.profile), ~blocked, eligible)
            .values(**bulk_to_fields(updated), status=JobStatus.RUNNING.value, completed_at=None)
            .execution_options(synchronize_session=False))
        if result.rowcount != 1:
            return False
        await self._session.execute(update(Task).where(Task.batch_job_id == str(job_id),
            Task.status == TaskStatus.PENDING.value, *no_evidence()).values(status=TaskStatus.QUEUED.value,
                waiting_reason=None, dispatch_revision=Task.dispatch_revision + 1))
        return True

    async def save_pause(self, job_id, expected_revision, reason):
        result = await self._session.execute(update(Job).where(Job.id == str(job_id),
            Job.bulk_revision == expected_revision, Job.status == JobStatus.RUNNING.value)
            .values(status=JobStatus.PAUSED.value, bulk_pause_reason=reason,
                    bulk_revision=Job.bulk_revision + 1).execution_options(synchronize_session=False))
        return result.rowcount == 1
