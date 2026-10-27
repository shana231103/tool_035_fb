# File: backend/app/domain/value_objects/bulk_import.py
"""Immutable imported-order identity and conditional dispatch contracts."""
from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any
from uuid import UUID
from app.domain.value_objects.enums import JobStatus, OwnerRole


def _hash(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("IMPORT_METADATA_INVALID")


def canonical_email(value: str) -> str:
    from app.domain.value_objects.email_address import EmailAddress
    normalized = EmailAddress.from_string(value.strip().casefold()).value
    if normalized != value:
        raise ValueError("IMPORT_METADATA_INVALID")
    return normalized


@dataclass(frozen=True)
class BulkReviewAcceptance:
    previous_profile_sha256: str
    accepted_profile_sha256: str
    review_sha256: str
    accepted_at: datetime

    def __post_init__(self):
        for value in (self.previous_profile_sha256, self.accepted_profile_sha256, self.review_sha256):
            _hash(value)
        if self.accepted_at.tzinfo is None:
            raise ValueError("IMPORT_METADATA_INVALID")


@dataclass(frozen=True)
class BulkImportMetadata:
    import_id: UUID
    request_sha256: str
    content_sha256: str
    accepted_profile_sha256: str
    ordered_mail_pool: tuple[str, ...]
    import_version: int = 1
    revision: int = 1
    last_acceptance: BulkReviewAcceptance | None = None
    pause_reason: str | None = None

    def __post_init__(self):
        for value in (self.request_sha256, self.content_sha256, self.accepted_profile_sha256):
            _hash(value)
        if (self.import_version != 1 or self.revision < 1 or
                not isinstance(self.ordered_mail_pool, tuple) or
                not 1 <= len(self.ordered_mail_pool) <= 100 or
                len(set(self.ordered_mail_pool)) != len(self.ordered_mail_pool)):
            raise ValueError("IMPORT_METADATA_INVALID")
        for email in self.ordered_mail_pool:
            canonical_email(email)


@dataclass(frozen=True)
class BulkTaskAssignment:
    sequence: int
    source_line: int
    assigned_mail_email: str

    def __post_init__(self):
        if not 1 <= self.sequence <= 1000 or self.source_line < 1:
            raise ValueError("IMPORT_METADATA_INVALID")
        canonical_email(self.assigned_mail_email)


@dataclass(frozen=True)
class ProfileSubmissionSnapshot:
    profile_id: UUID
    owner_name: str
    sender_name: str
    rights_jurisdiction: str
    owner_role: OwnerRole


@dataclass(frozen=True)
class AcceptedBulkReview:
    review_sha256: str
    profile_sha256: str
    profile: ProfileSubmissionSnapshot
    accepted_at: datetime
    previous_profile_sha256: str


@dataclass(frozen=True)
class ImportMatch:
    job_id: UUID
    import_id: UUID
    status: JobStatus
    revision: int
    submitted_count: int
    has_uncertain: bool


@dataclass(frozen=True)
class DispatchCursor:
    import_sequence: int | None
    created_at: datetime | None
    id: UUID


@dataclass(frozen=True)
class DispatchPage:
    tasks: tuple[Any, ...]
    next_cursor: DispatchCursor | None


@dataclass(frozen=True)
class AttemptClaim:
    task_id: UUID
    job_id: UUID
    expected_dispatch_revision: int
    expected_previous_attempt_id: str | None
    new_attempt_id: str
    snapshot: dict
    expected_job_revision: int | None
    expected_profile: ProfileSubmissionSnapshot
    expected_bulk_profile_sha256: str | None = None
    expected_profile_email: str | None = None


@dataclass(frozen=True)
class UnstartedClaimRestore:
    claim: AttemptClaim
    proven_no_provider: bool
    collector_joined: bool
