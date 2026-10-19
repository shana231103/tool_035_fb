# File: backend/app/domain/entities/report_task.py
"""Standalone ReportTask aggregate root representing an independent copyright report."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from app.domain.exceptions.domain_exceptions import InvalidStateTransitionError
from app.domain.value_objects.enums import ProxyCountry, TaskStatus
from app.domain.value_objects.explanation import ExplanationText
from app.domain.value_objects.original_url import OriginalUrl
from app.domain.value_objects.report_targets import ReportTargets
from app.domain.value_objects.target_url import TargetUrl
from app.domain.value_objects.task_execution import ExecutionGrant


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ReportTask:
    id: UUID
    operator_id: UUID
    owner_profile_id: UUID
    name: str
    targets: ReportTargets
    original_url: OriginalUrl
    explanation: ExplanationText
    preferred_country: Optional[ProxyCountry] = None
    status: TaskStatus = TaskStatus.DRAFT
    version: int = 1
    run_version: Optional[int] = None
    attempt_id: Optional[UUID] = None
    last_start_command_id: Optional[UUID] = None
    retry_count: int = 0
    max_retries: int = 3
    proxy_id: Optional[UUID] = None
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    completed_at: Optional[datetime] = None
    input_snapshot: dict = field(default_factory=dict)
    verification: dict = field(default_factory=dict)
    submitted_at: Optional[datetime] = None
    receipt_text: Optional[str] = None
    meta_case_number: Optional[str] = None
    screenshot_path: Optional[str] = None
    error_message: Optional[str] = None

    @classmethod
    def create(
        cls,
        operator_id: UUID,
        owner_profile_id: UUID,
        name: str,
        targets: ReportTargets,
        original_url: OriginalUrl,
        explanation: Optional[ExplanationText] = None,
        preferred_country: Optional[ProxyCountry] = None,
        task_id: Optional[UUID] = None,
        max_retries: int = 3,
    ) -> "ReportTask":
        now = _utc_now()
        return cls(
            id=task_id or uuid4(), operator_id=operator_id, owner_profile_id=owner_profile_id,
            name=name, targets=targets, original_url=original_url,
            explanation=explanation or ExplanationText.create_standard_dmca(),
            preferred_country=preferred_country, status=TaskStatus.DRAFT,
            version=1, retry_count=0, max_retries=max_retries, created_at=now, updated_at=now,
        )

    @property
    def target_url(self) -> TargetUrl:
        """First target URL for single-target compatibility."""
        return self.targets.items[0]

    @property
    def has_submission_evidence(self) -> bool:
        return any(v is not None for v in (self.submitted_at, self.receipt_text, self.meta_case_number, self.screenshot_path))

    @property
    def can_retry(self) -> bool:
        return self.status == TaskStatus.FAILED and not self.has_submission_evidence and self.retry_count < self.max_retries

    def admit_attempt(self, grant: ExecutionGrant) -> None:
        if self.status != TaskStatus.DRAFT or self.has_submission_evidence:
            raise InvalidStateTransitionError(f"Cannot admit attempt on task {self.id} with status {self.status}.")
        if grant.scope.task_id != self.id or grant.scope.operator_id != self.operator_id or grant.observed_task_version != self.version:
            raise InvalidStateTransitionError("Admission identity does not match task.")
        self.status, self.attempt_id = TaskStatus.PREPARING, grant.scope.attempt_id
        self.run_version, self.last_start_command_id = grant.scope.run_version, grant.admission_id
        self.version += 1
        self.updated_at = _utc_now()

    def mark_running(self, proxy_id: Optional[UUID] = None) -> None:
        if self.status not in (TaskStatus.PREPARING, TaskStatus.RUNNING):
            raise InvalidStateTransitionError(f"Cannot transition task {self.id} from {self.status} to RUNNING.")
        self.status = TaskStatus.RUNNING
        if proxy_id:
            self.proxy_id = proxy_id
        self.error_message = None
        self.version += 1
        self.updated_at = _utc_now()

    def mark_progress(self, status: TaskStatus, safe_metadata: Optional[dict] = None) -> None:
        valid_progress = (TaskStatus.RUNNING, TaskStatus.WAITING_EMAIL_CODE, TaskStatus.VERIFYING_EMAIL)
        if status not in valid_progress or self.status not in (TaskStatus.PREPARING, *valid_progress):
            raise InvalidStateTransitionError(f"Cannot progress task {self.id} from {self.status} to {status}.")
        self.status = status
        if safe_metadata:
            self.verification.update(safe_metadata)
        self.version += 1
        self.updated_at = _utc_now()

    def admit_submitting(self) -> None:
        if self.status not in (TaskStatus.RUNNING, TaskStatus.VERIFYING_EMAIL):
            raise InvalidStateTransitionError(f"Cannot transition task {self.id} from {self.status} to SUBMITTING.")
        self.status, self.submitted_at = TaskStatus.SUBMITTING, _utc_now()
        self.version += 1
        self.updated_at = _utc_now()

    def mark_submitted(
        self, *, receipt_text: str, case_number: Optional[str] = None,
        screenshot_path: Optional[str] = None,
    ) -> None:
        if not receipt_text.strip() or len(receipt_text.encode("utf-8")) > 16384:
            raise InvalidStateTransitionError("Confirmed receipt evidence is required.")
        if self.status not in (TaskStatus.SUBMITTING, TaskStatus.NEEDS_REVIEW, TaskStatus.SUBMITTED):
            raise InvalidStateTransitionError("Receipt is outside an admitted submission.")
        if self.status == TaskStatus.SUBMITTED:
            if self.receipt_text != receipt_text or self.meta_case_number != case_number:
                raise InvalidStateTransitionError("Conflicting receipt evidence.")
            return
        self.status = TaskStatus.SUBMITTED
        self.receipt_text, self.meta_case_number = receipt_text, case_number
        if screenshot_path:
            self.screenshot_path = screenshot_path
        self.error_message, self.completed_at = None, _utc_now()
        self.version += 1
        self.updated_at = _utc_now()

    def mark_failed(self, error: str, *, retryable: bool = True) -> None:
        if self.status == TaskStatus.SUBMITTED:
            return
        self.error_message = error
        if self.status in (TaskStatus.SUBMITTING, TaskStatus.NEEDS_REVIEW):
            self.status = TaskStatus.NEEDS_REVIEW
        else:
            self.status, self.completed_at = TaskStatus.FAILED, _utc_now()
        self.version += 1
        self.updated_at = _utc_now()

    def prepare_retry(self) -> None:
        if not self.can_retry:
            raise InvalidStateTransitionError("Only safe failed tasks within retry limit may be retried.")
        self.retry_count += 1
        self.status, self.completed_at, self.error_message = TaskStatus.DRAFT, None, None
        self.attempt_id, self.proxy_id = None, None
        self.verification, self.input_snapshot = {}, {}
        self.version += 1
        self.updated_at = _utc_now()

    def cancel(self) -> None:
        if self.status == TaskStatus.SUBMITTED:
            raise InvalidStateTransitionError("Cannot cancel an already submitted task.")
        if self.status in (TaskStatus.SUBMITTING, TaskStatus.NEEDS_REVIEW):
            self.status = TaskStatus.NEEDS_REVIEW
        else:
            self.status, self.completed_at = TaskStatus.CANCELLED, _utc_now()
        self.version += 1
        self.updated_at = _utc_now()
