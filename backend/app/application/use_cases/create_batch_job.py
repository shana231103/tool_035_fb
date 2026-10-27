# File: backend/app/application/use_cases/create_batch_job.py
import asyncio
from dataclasses import astuple
import logging
from typing import Callable
from uuid import UUID
from app.application.dtos.job_dtos import BatchJobResponseDTO, CreateBatchJobRequestDTO
from app.application.job_serialization import job_to_dto
from app.application.unit_of_work import IUnitOfWork
from app.domain.entities.batch_job import BatchJob
from app.domain.entities.report_task import ReportTask
from app.domain.exceptions.domain_exceptions import EntityNotFoundError
from app.domain.ports.storage_service import IStorageService
from app.domain.value_objects.enums import PlatformType
from app.domain.value_objects.explanation import ExplanationText
from app.domain.value_objects.original_url import OriginalUrl
from app.domain.value_objects.target_url import TargetUrl

logger = logging.getLogger(__name__)


async def _drain_compensation(task: asyncio.Task):
    cancelled = None
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError as error:
            cancelled = cancelled or error
    task.result()
    return cancelled


class CreateBatchJobUseCase:
    def __init__(self, uow_factory: Callable[[], IUnitOfWork], storage: IStorageService):
        self._uow_factory = uow_factory
        self._storage = storage

    async def execute(
        self, command: CreateBatchJobRequestDTO, proof_file_bytes: bytes | None = None,
        proof_filename: str | None = None,
    ) -> BatchJobResponseDTO:
        async with self._uow_factory() as uow:
            profile = await uow.profiles.get_by_id(command.owner_profile_id)
            if not profile:
                raise EntityNotFoundError("Owner profile not found.")
            profile.validate_for_submission()
            validated_profile = astuple(profile)
        job = self._build_job(command)
        if (proof_file_bytes is None) != (proof_filename is None):
            raise ValueError("Evidence filename and content must be supplied together.")
        reference = None
        if proof_file_bytes is not None:
            reference = await self._storage.save_proof_file(proof_filename, proof_file_bytes)
        commit_uncertain = False
        try:
            async with self._uow_factory() as uow:
                current_profile = await uow.profiles.get_by_id(command.owner_profile_id)
                if not current_profile:
                    raise EntityNotFoundError("Owner profile not found.")
                current_profile.validate_for_submission()
                if astuple(current_profile) != validated_profile:
                    raise ValueError("Owner profile changed. Review it and create the job again.")
                await uow.jobs.save(job)
                result = job_to_dto(job)
                commit_uncertain = True
            return result
        except (Exception, asyncio.CancelledError) as error:
            if reference:
                compensation = asyncio.create_task(self._compensate_proof(job.id, reference, commit_uncertain))
                cancelled = await _drain_compensation(compensation)
                if cancelled and not isinstance(error, asyncio.CancelledError):
                    raise cancelled
            raise

    @staticmethod
    def _build_job(command: CreateBatchJobRequestDTO) -> BatchJob:
        original = OriginalUrl.from_raw_url(command.original_work_url)
        if command.custom_explanation is not None and not command.custom_explanation.strip():
            raise ValueError("Custom explanation must not be blank.")
        job = BatchJob.create(
            name=command.name, owner_profile_id=command.owner_profile_id,
            preferred_country=command.preferred_country, concurrency=command.concurrency,
            delay_min=command.delay_min, delay_max=command.delay_max,
        )
        valid_targets = []
        for raw_url in command.target_urls:
            if not raw_url or not raw_url.strip():
                continue
            target = TargetUrl.from_raw_url(raw_url.strip())
            if target.platform != PlatformType.FACEBOOK:
                raise ValueError("This workflow only supports Facebook Copyright targets.")
            valid_targets.append(target)
        if not valid_targets:
            raise ValueError("At least one Facebook target is required.")

        chunk_size = 30
        for i in range(0, len(valid_targets), chunk_size):
            chunk = valid_targets[i : i + chunk_size]
            joined_url = ", ".join(t.url for t in chunk)
            content_types = {t.content_type for t in chunk}
            content_type = chunk[0].content_type if len(content_types) == 1 else "post"
            batched_target = TargetUrl(url=joined_url, platform=PlatformType.FACEBOOK, content_type=content_type)
            explanation = (
                ExplanationText.custom(command.custom_explanation)
                if command.custom_explanation is not None
                else ExplanationText.create_standard_dmca(batched_target.content_type)
            )
            job.add_task(ReportTask.create(
                batch_job_id=job.id, target_url=batched_target, original_url=original,
                explanation=explanation, infringing_account=chunk[0].extract_account_identifier(),
            ))
        return job

    async def _compensate_proof(self, job_id: UUID, reference: str, commit_uncertain: bool) -> None:
        if commit_uncertain:
            try:
                async with self._uow_factory() as uow:
                    committed = await uow.jobs.get_by_id(job_id)
                if committed is not None:
                    return
            except (Exception, asyncio.CancelledError):
                logger.warning("Proof retained for reconciliation: job=%s reason=OUTCOME_UNKNOWN", job_id)
                return
        try:
            await self._storage.delete_proof_file(reference)
        except (Exception, asyncio.CancelledError):
            logger.warning("Proof retained for reconciliation: job=%s reason=CLEANUP_FAILED", job_id)
