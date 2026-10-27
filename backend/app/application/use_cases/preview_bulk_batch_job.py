# File: backend/app/application/use_cases/preview_bulk_batch_job.py
from uuid import UUID
from app.application.bulk_import_canonical import (
    canonical_content_sha256, canonical_pool, canonical_request_sha256, duplicate_ack_sha256,
    mask_email, normalized_settings, preview_digest, validate_mail_pool,
)
from app.application.bulk_import_models import (
    BulkImportError, BulkPreview, CreateBulkBatchCommand, MaskedAssignment,
)
from app.application.bulk_import_review import profile_sha256, profile_submission_snapshot
from app.application.bulk_order_import import parse_bulk_orders


class PreviewBulkBatchJobUseCase:
    def __init__(self, uow_factory, connections):
        self._uow_factory, self._connections = uow_factory, connections

    async def execute(self, command):
        try:
            rows = parse_bulk_orders(command.orders_text)
        except BulkImportError as error:
            if not error.errors:
                raise
            return BulkPreview((), (), (), "", "", (), None, error.errors, False)
        _, explanation = normalized_settings(command)
        pool = canonical_pool(command.mailboxes)
        async with self._uow_factory() as uow:
            profile = await uow.profiles.get_by_id(command.profile_id)
            if profile is None:
                raise BulkImportError("PROFILE_REVIEW_REQUIRED", status_code=409)
            try:
                snapshot = profile_submission_snapshot(profile)
            except ValueError:
                raise BulkImportError("PROFILE_REVIEW_REQUIRED", status_code=409) from None
            content_hash = canonical_content_sha256(command.profile_id, rows, explanation)
            matches = await uow.bulk_imports.find_content_matches(content_hash)
        bindings = await validate_mail_pool(command.mailboxes, self._connections)
        profile_hash = profile_sha256(snapshot)
        stable = CreateBulkBatchCommand(UUID(int=0), command, profile_hash, "")
        request_hash = canonical_request_sha256(stable)
        assignments = tuple(MaskedAssignment(row.sequence, row.source_line,
            mask_email(pool[(row.sequence - 1) % len(pool)])) for row in rows)
        return BulkPreview(rows, assignments, (), profile_hash,
            preview_digest(request_hash, profile_hash, bindings), matches,
            duplicate_ack_sha256(content_hash, matches), (), True)
