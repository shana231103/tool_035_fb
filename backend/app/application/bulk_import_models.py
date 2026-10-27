# File: backend/app/application/bulk_import_models.py
from dataclasses import dataclass
from uuid import UUID
from app.domain.value_objects.bulk_import import ProfileSubmissionSnapshot
from app.domain.value_objects.enums import ProxyCountry


@dataclass(frozen=True)
class BulkRowError:
    source_line: int
    reason: str


class BulkImportError(ValueError):
    def __init__(self, reason: str, *, status_code: int = 422, errors=()):
        super().__init__(reason)
        self.reason, self.status_code, self.errors = reason, status_code, tuple(errors)


@dataclass(frozen=True)
class BulkOrderRow:
    sequence: int
    source_line: int
    original_url: str
    target_urls: tuple[str, ...]


@dataclass(frozen=True)
class BulkMailboxRef:
    source_line: int
    expected_email: str
    connection_id: UUID


@dataclass(frozen=True)
class BulkPreviewCommand:
    name: str
    profile_id: UUID
    orders_text: str
    mailboxes: tuple[BulkMailboxRef, ...]
    preferred_country: ProxyCountry | None = None
    custom_explanation: str | None = None


@dataclass(frozen=True)
class CreateBulkBatchCommand:
    import_id: UUID
    preview: BulkPreviewCommand
    expected_profile_sha256: str
    preview_sha256: str
    duplicate_ack_sha256: str | None = None


@dataclass(frozen=True)
class MaskedAssignment:
    sequence: int
    source_line: int
    masked_email: str


@dataclass(frozen=True)
class BulkPreview:
    normalized_orders: tuple[BulkOrderRow, ...]
    masked_assignments: tuple[MaskedAssignment, ...]
    excluded_rows: tuple[BulkRowError, ...]
    profile_sha256: str
    preview_sha256: str
    content_matches: tuple
    duplicate_ack_sha256: str | None
    errors: tuple[BulkRowError, ...]
    can_create: bool


@dataclass(frozen=True)
class BulkStartReview:
    job_id: UUID
    bulk_revision: int
    status: str
    profile_sha256: str
    pending_tasks_digest: str
    mail_readiness_digest: str
    review_sha256: str
    waiting_counts: dict[str, int]
    blocked_reasons: tuple[str, ...]
    can_start: bool
    profile_snapshot: ProfileSubmissionSnapshot


@dataclass(frozen=True)
class BulkCreateResult:
    import_id: UUID
    job_id: UUID
    replayed: bool
    safe_job_view: object
