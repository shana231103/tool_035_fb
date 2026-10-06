# File: backend/app/domain/entities/report_task.py
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4
from app.domain.exceptions.domain_exceptions import InvalidStateTransitionError
from app.domain.value_objects.enums import TaskStatus
from app.domain.value_objects.explanation import ExplanationText
from app.domain.value_objects.original_url import OriginalUrl
from app.domain.value_objects.target_url import TargetUrl


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ReportTask:
    id: UUID
    batch_job_id: UUID
    target_url: TargetUrl
    original_url: OriginalUrl
    explanation: ExplanationText
    status: TaskStatus = TaskStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    proxy_id: Optional[UUID] = None
    meta_case_number: Optional[str] = None
    screenshot_path: Optional[str] = None
    error_message: Optional[str] = None
    infringing_account: Optional[str] = None
    created_at: datetime = field(default_factory=_utc_now)
    completed_at: Optional[datetime] = None
    attempt_id: Optional[str] = None
    input_snapshot: dict = field(default_factory=dict)
    verification: dict = field(default_factory=dict)
    submitted_at: Optional[datetime] = None
    receipt_text: Optional[str] = None

    @classmethod
    def create(
        cls,
        batch_job_id: UUID,
        target_url: TargetUrl,
        original_url: OriginalUrl,
        explanation: Optional[ExplanationText] = None,
        infringing_account: Optional[str] = None,
        task_id: Optional[UUID] = None,
    ) -> "ReportTask":
        return cls(
            id=task_id or uuid4(),
            batch_job_id=batch_job_id,
            target_url=target_url,
            original_url=original_url,
            explanation=explanation or ExplanationText.create_standard_dmca(),
            infringing_account=infringing_account,
            status=TaskStatus.PENDING,
            created_at=_utc_now(),
        )

    def mark_queued(self) -> None:
        if self.status in [TaskStatus.SUBMITTED, TaskStatus.NEEDS_REVIEW, TaskStatus.SUBMITTING]:
            raise InvalidStateTransitionError("Cannot queue an already submitted task.")
        self.status = TaskStatus.QUEUED

    @property
    def has_submission_evidence(self) -> bool:
        return any(value is not None for value in
                   (self.submitted_at, self.receipt_text, self.meta_case_number, self.screenshot_path))

    @property
    def can_retry_failed(self) -> bool:
        return (self.status == TaskStatus.FAILED and not self.has_submission_evidence
                and self.retry_count < self.max_retries)

    def retry_failed(self) -> None:
        if not self.can_retry_failed:
            raise InvalidStateTransitionError("Only safe failed tasks within the retry limit may be retried.")
        self.retry_count += 1
        self.status = TaskStatus.PENDING
        self.completed_at = self.error_message = self.attempt_id = self.proxy_id = None
        self.verification = {}
        self.input_snapshot = {}

    def mark_running(self, proxy_id: Optional[UUID] = None) -> None:
        if self.status not in [TaskStatus.QUEUED, TaskStatus.PENDING, TaskStatus.RUNNING]:
            raise InvalidStateTransitionError(
                f"Cannot transition task {self.id} from {self.status} to RUNNING."
            )
        self.status = TaskStatus.RUNNING
        self.proxy_id = proxy_id
        self.error_message = None

    def mark_submitted(self, case_number: Optional[str], screenshot_path: Optional[str]) -> None:
        self.status = TaskStatus.SUBMITTED
        self.meta_case_number = case_number
        self.screenshot_path = screenshot_path
        self.error_message = None
        self.completed_at = _utc_now()

    def mark_failed(self, error: str, retryable: bool = True) -> bool:
        if self.status == TaskStatus.SUBMITTED:
            return False
        self.error_message = error
        if self.status in (TaskStatus.SUBMITTING, TaskStatus.NEEDS_REVIEW):
            self.status = TaskStatus.NEEDS_REVIEW
            return False
        if retryable and self.retry_count < self.max_retries:
            self.retry_count += 1
            self.status = TaskStatus.QUEUED
            return True  # Can retry
        self.status = TaskStatus.FAILED
        self.completed_at = _utc_now()
        return False  # Terminal failure

    def cancel(self) -> None:
        if self.status in (TaskStatus.SUBMITTING, TaskStatus.NEEDS_REVIEW):
            self.status = TaskStatus.NEEDS_REVIEW
        elif self.status != TaskStatus.SUBMITTED:
            self.status = TaskStatus.CANCELLED
            self.completed_at = _utc_now()
