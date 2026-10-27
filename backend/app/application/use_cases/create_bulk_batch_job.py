# File: backend/app/application/use_cases/create_bulk_batch_job.py
import asyncio
from app.application.bulk_import_canonical import (
    canonical_content_sha256, canonical_pool, canonical_request_sha256, duplicate_ack_sha256,
    normalized_settings, preview_digest, validate_mail_pool,
)
from app.application.bulk_import_models import BulkCreateResult, BulkImportError
from app.application.bulk_import_review import profile_sha256, profile_submission_snapshot
from app.application.bulk_order_import import parse_bulk_orders
from app.application.job_serialization import job_to_dto
from app.domain.entities.batch_job import BatchJob
from app.domain.entities.report_task import ReportTask
from app.domain.value_objects.bulk_import import BulkImportMetadata, BulkTaskAssignment
from app.domain.value_objects.enums import PlatformType
from app.domain.value_objects.explanation import ExplanationText
from app.domain.value_objects.original_url import OriginalUrl
from app.domain.value_objects.target_url import TargetUrl


class CreateBulkBatchJobUseCase:
    def __init__(self, uow_factory, connections):
        self._uow_factory, self._connections = uow_factory, connections

    async def lookup(self, import_id):
        async with self._uow_factory() as uow:
            job = await uow.bulk_imports.get_by_import_id(import_id)
        return self._result(job, True) if job is not None else None

    async def execute(self, command):
        request_hash = canonical_request_sha256(command)
        replay = await self._replay(command.import_id, request_hash)
        if replay:
            return replay
        rows = parse_bulk_orders(command.preview.orders_text)
        name, explanation = normalized_settings(command.preview)
        pool = canonical_pool(command.preview.mailboxes)
        bindings = await validate_mail_pool(command.preview.mailboxes, self._connections)
        expected_preview = preview_digest(request_hash, command.expected_profile_sha256, bindings)
        if expected_preview != command.preview_sha256:
            raise BulkImportError("STALE_PREVIEW", status_code=409)
        content_hash = canonical_content_sha256(command.preview.profile_id, rows, explanation)
        job = self._build(command, rows, name, explanation, pool, request_hash, content_hash)
        try:
            async with self._uow_factory() as uow:
                existing = await uow.bulk_imports.get_by_import_id(command.import_id)
                if existing is not None:
                    return self._check_replay(existing, request_hash)
                profile = await uow.profiles.get_by_id(command.preview.profile_id)
                if profile is None:
                    raise BulkImportError("PROFILE_REVIEW_REQUIRED", status_code=409)
                try:
                    actual_profile = profile_sha256(profile_submission_snapshot(profile))
                except ValueError:
                    raise BulkImportError("PROFILE_REVIEW_REQUIRED", status_code=409) from None
                if actual_profile != command.expected_profile_sha256:
                    raise BulkImportError("STALE_PREVIEW", status_code=409)
                matches = await uow.bulk_imports.find_content_matches(content_hash)
                acknowledgement = duplicate_ack_sha256(content_hash, matches)
                if acknowledgement and command.duplicate_ack_sha256 != acknowledgement:
                    raise BulkImportError("DUPLICATE_ACK_REQUIRED", status_code=409)
                await uow.bulk_imports.insert_draft(job)
            return self._result(job, False)
        except BulkImportError:
            # A concurrent same-key writer may have committed after our first read,
            # and can now appear in duplicate history. Reconcile outside the rolled
            # back transaction before returning a stale/ack conflict.
            try:
                replay = await self._replay(command.import_id, request_hash)
            except BulkImportError:
                raise
            except (Exception, asyncio.CancelledError):
                raise BulkImportError("IMPORT_OUTCOME_UNKNOWN", status_code=503) from None
            if replay:
                return replay
            raise
        except (Exception, asyncio.CancelledError):
            try:
                replay = await self._replay(command.import_id, request_hash)
            except BulkImportError:
                raise
            except (Exception, asyncio.CancelledError):
                raise BulkImportError("IMPORT_OUTCOME_UNKNOWN", status_code=503) from None
            if replay:
                return replay
            raise BulkImportError("IMPORT_OUTCOME_UNKNOWN", status_code=503) from None

    async def _replay(self, import_id, request_hash):
        async with self._uow_factory() as uow:
            job = await uow.bulk_imports.get_by_import_id(import_id)
        return self._check_replay(job, request_hash) if job is not None else None

    @classmethod
    def _check_replay(cls, job, request_hash):
        if job.bulk.request_sha256 != request_hash:
            raise BulkImportError("IMPORT_KEY_CONFLICT", status_code=409)
        return cls._result(job, True)

    @staticmethod
    def _result(job, replayed):
        return BulkCreateResult(job.bulk.import_id, job.id, replayed, job_to_dto(job))

    @staticmethod
    def _build(command, rows, name, explanation, pool, request_hash, content_hash):
        job = BatchJob.create(name, command.preview.profile_id,
                              preferred_country=command.preview.preferred_country, concurrency=3)
        job.bulk = BulkImportMetadata(command.import_id, request_hash, content_hash,
                                     command.expected_profile_sha256, pool)
        for row in rows:
            targets = [TargetUrl.from_raw_url(url) for url in row.target_urls]
            types = {target.content_type for target in targets}
            target = TargetUrl(", ".join(row.target_urls), PlatformType.FACEBOOK,
                               targets[0].content_type if len(types) == 1 else "post")
            text = ExplanationText.custom(explanation) if explanation is not None else (
                ExplanationText.create_standard_dmca(target.content_type))
            task = ReportTask.create(job.id, target, OriginalUrl.from_raw_url(row.original_url),
                                     text, targets[0].extract_account_identifier())
            task.assignment = BulkTaskAssignment(row.sequence, row.source_line,
                                                pool[(row.sequence - 1) % len(pool)])
            job.add_task(task)
        return job
