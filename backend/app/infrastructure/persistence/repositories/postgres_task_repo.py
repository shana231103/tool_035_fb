# File: backend/app/infrastructure/persistence/repositories/postgres_task_repo.py
from typing import List, Optional
from uuid import UUID
from sqlalchemy import and_, exists, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.entities.report_task import ReportTask
from app.domain.ports.repositories import IReportTaskRepository
from app.domain.value_objects.enums import TaskStatus
from app.infrastructure.persistence.mappers import DataMapper
from app.infrastructure.persistence.models import ReportTaskModel
from app.infrastructure.persistence.models import BatchJobModel
from app.domain.value_objects.bulk_import import DispatchCursor, DispatchPage
from app.infrastructure.persistence.bulk_import_mapping import assignment_from_model
from app.infrastructure.persistence.repositories.bulk_import_repo import no_evidence, profile_matches


class PostgresTaskRepository(IReportTaskRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, task_id: UUID) -> Optional[ReportTask]:
        model = await self._session.get(ReportTaskModel, str(task_id))
        return DataMapper.task_to_domain(model) if model else None

    async def save(self, task: ReportTask) -> None:
        model = await self._session.get(ReportTaskModel, str(task.id), populate_existing=True)
        if not model:
            self._session.add(DataMapper.task_to_model(task))
        else:
            if (assignment_from_model(model) != task.assignment or task.dispatch_revision < model.dispatch_revision
                    or (task.attempt_id != model.attempt_id and task.dispatch_revision <= model.dispatch_revision)):
                raise ValueError("Stale task state.")
            if any(getattr(model, key) is not None and getattr(model, key) != getattr(task, key)
                   for key in ("submitted_at", "receipt_text", "meta_case_number", "screenshot_path")):
                raise ValueError("Submission evidence cannot be overwritten.")
            if (model.input_snapshot and task.attempt_id == model.attempt_id and
                    task.dispatch_revision == model.dispatch_revision and task.input_snapshot != model.input_snapshot):
                raise ValueError("Attempt snapshot is immutable.")
            mapped = DataMapper.task_to_model(task)
            keys = ("status", "retry_count", "proxy_id", "meta_case_number", "screenshot_path",
                    "error_message", "infringing_account", "completed_at", "attempt_id", "input_snapshot",
                    "verification", "submitted_at", "receipt_text", "dispatch_revision", "waiting_reason")
            table = ReportTaskModel
            evidence = [getattr(table, key) == getattr(model, key) for key in
                        ("submitted_at", "receipt_text", "meta_case_number", "screenshot_path")]
            result = await self._session.execute(update(table).where(table.id == str(task.id),
                table.attempt_id == model.attempt_id, table.dispatch_revision == model.dispatch_revision,
                table.status == model.status, *evidence).values(**{key: getattr(mapped, key) for key in keys})
                .execution_options(synchronize_session=False))
            if result.rowcount != 1:
                raise ValueError("Stale task state.")
            self._session.expire(model)

    async def list_dispatch_candidates(self, job_id, cursor=None, limit=100):
        task = ReportTaskModel
        bulk = await self._session.scalar(select(BatchJobModel.bulk_import_id).where(BatchJobModel.id == str(job_id)))
        ordering = task.bulk_sequence if bulk else task.created_at
        conditions = [task.batch_job_id == str(job_id), task.status == TaskStatus.QUEUED.value, *no_evidence()]
        if cursor:
            value = cursor.import_sequence if bulk else cursor.created_at
            if value is None:
                raise ValueError("Invalid dispatch cursor.")
            conditions.append(or_(ordering > value, and_(ordering == value, task.id > str(cursor.id))))
        size = min(max(limit, 1), 100)
        result = await self._session.execute(select(task).where(*conditions).order_by(ordering, task.id).limit(size + 1))
        models = result.scalars().all()
        selected = models[:size]
        next_cursor = None
        if len(models) > size:
            last = selected[-1]
            next_cursor = DispatchCursor(last.bulk_sequence if bulk else None,
                                         None if bulk else last.created_at, UUID(last.id))
        return DispatchPage(tuple(DataMapper.task_to_domain(model) for model in selected), next_cursor)

    async def claim_attempt(self, claim):
        task, job = ReportTaskModel, BatchJobModel
        snapshot_email = claim.snapshot.get("owner_email")
        profile = claim.expected_profile
        conditions = [job.id == str(claim.job_id), job.status == "RUNNING",
                      job.owner_profile_id == str(profile.profile_id)]
        if claim.expected_job_revision is not None:
            conditions.extend([job.bulk_revision == claim.expected_job_revision,
                job.bulk_profile_sha256 == claim.expected_bulk_profile_sha256,
                job.bulk_import_id.is_not(None)])
            email_condition = task.assigned_mail_email == snapshot_email if snapshot_email else False
            profile_condition = profile_matches(profile)
        else:
            conditions.append(job.bulk_import_id.is_(None))
            email_condition = task.assigned_mail_email.is_(None)
            if not claim.expected_profile_email or snapshot_email != claim.expected_profile_email:
                return False
            profile_condition = profile_matches(profile, claim.expected_profile_email)
        result = await self._session.execute(update(task).where(task.id == str(claim.task_id),
            task.batch_job_id == str(claim.job_id), task.status == TaskStatus.QUEUED.value,
            task.attempt_id == claim.expected_previous_attempt_id,
            task.dispatch_revision == claim.expected_dispatch_revision, *no_evidence(), email_condition,
            exists(select(job.id).where(*conditions)), profile_condition)
            .values(status=TaskStatus.RUNNING.value, attempt_id=claim.new_attempt_id,
                input_snapshot=dict(claim.snapshot), dispatch_revision=task.dispatch_revision + 1,
                error_message=None, waiting_reason=None, completed_at=None)
            .execution_options(synchronize_session=False))
        return result.rowcount == 1

    async def restore_unstarted(self, restore):
        if not restore.proven_no_provider or not restore.collector_joined:
            return False
        claim, task = restore.claim, ReportTaskModel
        result = await self._session.execute(update(task).where(task.id == str(claim.task_id),
            task.batch_job_id == str(claim.job_id), task.status == TaskStatus.RUNNING.value,
            task.attempt_id == claim.new_attempt_id,
            task.dispatch_revision == claim.expected_dispatch_revision + 1, *no_evidence())
            .values(status=TaskStatus.QUEUED.value, attempt_id=claim.expected_previous_attempt_id,
                    input_snapshot={}, dispatch_revision=task.dispatch_revision + 1)
            .execution_options(synchronize_session=False))
        return result.rowcount == 1

    async def save_wait_reason(self, task_id, expected_revision, reason):
        task = ReportTaskModel
        result = await self._session.execute(update(task).where(task.id == str(task_id),
            task.status == TaskStatus.QUEUED.value, task.dispatch_revision == expected_revision,
            *no_evidence()).values(waiting_reason=reason).execution_options(synchronize_session=False))
        return result.rowcount == 1

    async def get_next_queued_tasks(self, job_id: UUID, limit: int = 10) -> List[ReportTask]:
        stmt = (
            select(ReportTaskModel)
            .where(
                ReportTaskModel.batch_job_id == str(job_id),
                ReportTaskModel.status.in_([TaskStatus.QUEUED.value, TaskStatus.PENDING.value]),
            )
            .order_by(ReportTaskModel.created_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [DataMapper.task_to_domain(m) for m in models]

    async def list_tasks_by_job(self, job_id: UUID) -> List[ReportTask]:
        stmt = (
            select(ReportTaskModel)
            .where(ReportTaskModel.batch_job_id == str(job_id))
            .order_by(ReportTaskModel.created_at)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [DataMapper.task_to_domain(m) for m in models]
