# File: backend/app/application/use_cases/create_report_task.py
"""Create an owned draft and optional archival proof without launching execution."""
from app.application.request_authority import RequestAuthorityGuard
from app.application.task_artifacts import TaskArtifacts
from app.application.task_records import TaskView
from app.domain.entities.report_task import ReportTask
from app.domain.exceptions.domain_exceptions import EntityNotFoundError
from app.domain.value_objects.explanation import ExplanationText
from app.domain.value_objects.original_url import OriginalUrl
from app.domain.value_objects.report_targets import ReportTargets
from app.domain.value_objects.enums import OwnerRole
from uuid import uuid4


class _UtcClock:
    def now(self):
        from datetime import datetime, timezone
        return datetime.now(timezone.utc)


class CreateReportTaskUseCase:
    def __init__(self, uow_factory, storage_service=None, authority=None):
        self._uow_factory = uow_factory
        self._authority = authority or RequestAuthorityGuard(_UtcClock())
        self._artifacts = TaskArtifacts(uow_factory, storage_service)

    async def execute(self, principal, command, proof=None) -> TaskView:
        targets = ReportTargets.from_urls(command.target_urls)
        original = OriginalUrl.from_raw_url(command.original_url)
        explanation = ExplanationText.custom(command.explanation)
        task_id = uuid4()
        return await self._artifacts.own(self._create(principal, command, proof, task_id, targets, original, explanation))

    async def _create(self, principal, command, proof, task_id, targets, original, explanation):
        record = await self._artifacts.stage(principal.operator_id, task_id, proof)
        try:
            async with self._uow_factory.request(principal) as uow:
                await self._authority.validate_request_write(uow, principal)
                profile = await uow.profiles.get_by_id(command.owner_profile_id)
                if profile is None or profile.operator_id != principal.operator_id:
                    raise EntityNotFoundError("Profile not found")
                if profile.owner_role != OwnerRole.OWNER:
                    raise ValueError("A rights owner profile is required.")
                task = ReportTask.create(principal.operator_id, command.owner_profile_id,
                    command.name or "Report Task", targets, original, explanation,
                    command.preferred_country, task_id)
                await uow.tasks.insert(task)
                await self._artifacts.attach(uow, record)
                await uow.commit()
        except BaseException:
            await self._artifacts.compensate_known_absent(principal.operator_id, task_id, record)
            raise
        return TaskView(id=task.id, operator_id=task.operator_id, name=task.name,
            status=task.status, version=task.version, target_urls=tuple(task.targets.urls),
            target_count=len(task.targets.urls), original_url=task.original_url.url,
            explanation=task.explanation.content, owner_profile_id=task.owner_profile_id,
            preferred_country=task.preferred_country, retry_count=task.retry_count,
            max_retries=task.max_retries, created_at=task.created_at, updated_at=task.updated_at)

    async def shutdown(self, deadline=None):
        await self._artifacts.shutdown(deadline)
