# File: backend/app/infrastructure/persistence/bulk_import_mapping.py
"""Validate complete durable import identity; never infer missing metadata."""
from datetime import datetime
from uuid import UUID
from app.domain.value_objects.bulk_import import BulkImportMetadata, BulkReviewAcceptance, BulkTaskAssignment

JOB_FIELDS = ("bulk_import_id", "bulk_import_version", "bulk_request_sha256", "bulk_content_sha256",
              "bulk_profile_sha256", "bulk_mail_pool", "bulk_revision")
TASK_FIELDS = ("bulk_sequence", "bulk_source_line", "assigned_mail_email")


def bulk_from_model(model):
    values = [getattr(model, key) for key in JOB_FIELDS]
    if all(value is None for value in values):
        if model.bulk_last_acceptance is not None or model.bulk_pause_reason is not None:
            raise ValueError("IMPORT_METADATA_INVALID")
        return None
    if any(value is None for value in values) or not isinstance(model.bulk_mail_pool, list):
        raise ValueError("IMPORT_METADATA_INVALID")
    acceptance = model.bulk_last_acceptance
    if acceptance is not None:
        try:
            acceptance = BulkReviewAcceptance(acceptance["previous_profile_sha256"],
                acceptance["accepted_profile_sha256"], acceptance["review_sha256"],
                datetime.fromisoformat(acceptance["accepted_at"]))
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("IMPORT_METADATA_INVALID") from error
    return BulkImportMetadata(UUID(model.bulk_import_id), model.bulk_request_sha256,
        model.bulk_content_sha256, model.bulk_profile_sha256, tuple(model.bulk_mail_pool),
        model.bulk_import_version, model.bulk_revision, acceptance, model.bulk_pause_reason)


def bulk_to_fields(bulk):
    fields = dict.fromkeys((*JOB_FIELDS, "bulk_last_acceptance", "bulk_pause_reason"))
    if bulk is None:
        return fields
    fields.update(bulk_import_id=str(bulk.import_id), bulk_import_version=bulk.import_version,
        bulk_request_sha256=bulk.request_sha256, bulk_content_sha256=bulk.content_sha256,
        bulk_profile_sha256=bulk.accepted_profile_sha256, bulk_mail_pool=list(bulk.ordered_mail_pool),
        bulk_revision=bulk.revision, bulk_pause_reason=bulk.pause_reason)
    if bulk.last_acceptance:
        acceptance = bulk.last_acceptance
        fields["bulk_last_acceptance"] = dict(previous_profile_sha256=acceptance.previous_profile_sha256,
            accepted_profile_sha256=acceptance.accepted_profile_sha256, review_sha256=acceptance.review_sha256,
            accepted_at=acceptance.accepted_at.isoformat())
    return fields


def assignment_from_model(model):
    values = [getattr(model, key) for key in TASK_FIELDS]
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise ValueError("IMPORT_METADATA_INVALID")
    return BulkTaskAssignment(*values)


def assignment_to_fields(assignment):
    values = (assignment.sequence, assignment.source_line, assignment.assigned_mail_email) if assignment else (None,) * 3
    return dict(zip(TASK_FIELDS, values))


def validate_job_assignments(job):
    if job.bulk is None:
        if any(task.assignment is not None for task in job.tasks):
            raise ValueError("IMPORT_METADATA_INVALID")
        return
    pool = job.bulk.ordered_mail_pool
    assignments = sorted((task.assignment for task in job.tasks), key=lambda item: item.sequence if item else 0)
    if not 1 <= len(assignments) <= 1000:
        raise ValueError("IMPORT_METADATA_INVALID")
    for sequence, assignment in enumerate(assignments, 1):
        if (assignment is None or assignment.sequence != sequence or
                assignment.assigned_mail_email != pool[(sequence - 1) % len(pool)]):
            raise ValueError("IMPORT_METADATA_INVALID")
