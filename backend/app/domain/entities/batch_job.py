# File: backend/app/domain/entities/batch_job.py
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID, uuid4
from app.domain.entities.report_task import ReportTask
from app.domain.value_objects.enums import JobStatus, ProxyCountry, TaskStatus


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class BatchJob:
    id: UUID
    name: str
    owner_profile_id: UUID
    preferred_country: Optional[ProxyCountry]
    concurrency: int = 1
    delay_min: int = 0
    delay_max: int = 0
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = field(default_factory=_utc_now)
    completed_at: Optional[datetime] = None
    tasks: List[ReportTask] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        name: str,
        owner_profile_id: UUID,
        preferred_country: Optional[ProxyCountry] = None,
        concurrency: int = 1,
        delay_min: int = 0,
        delay_max: int = 0,
        job_id: Optional[UUID] = None,
    ) -> "BatchJob":
        clean_name = (name or "").strip()
        if not clean_name:
            raise ValueError("Batch job name cannot be empty.")
        if concurrency < 1 or concurrency > 10:
            raise ValueError("Concurrency must be between 1 and 10.")
        if delay_min < 0 or delay_max < delay_min:
            raise ValueError("Invalid delay range: min must be >= 0 and <= max.")

        return cls(
            id=job_id or uuid4(),
            name=clean_name,
            owner_profile_id=owner_profile_id,
            preferred_country=preferred_country,
            concurrency=concurrency,
            delay_min=delay_min,
            delay_max=delay_max,
            status=JobStatus.PENDING,
            created_at=_utc_now(),
        )

    def add_task(self, task: ReportTask) -> None:
        self.tasks.append(task)

    def start(self) -> None:
        self.status = JobStatus.RUNNING
        for t in self.tasks:
            if t.status == TaskStatus.PENDING:
                t.mark_queued()

    def pause(self) -> None:
        if self.is_terminal or self.status == JobStatus.PAUSED:
            return
        self.status = JobStatus.PAUSED

    @property
    def is_terminal(self) -> bool:
        return self.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)

    def cancel(self) -> None:
        self.status = JobStatus.CANCELLED
        self.completed_at = _utc_now()
        for t in self.tasks:
            t.cancel()

    def update_completion_status(self) -> None:
        if self.is_terminal or not self.tasks:
            return
        all_finished = all(
            t.status in [TaskStatus.SUBMITTED, TaskStatus.FAILED, TaskStatus.CANCELLED]
            for t in self.tasks
        )
        if all_finished:
            if any(t.status == TaskStatus.SUBMITTED for t in self.tasks):
                self.status = JobStatus.COMPLETED
            elif all(t.status == TaskStatus.CANCELLED for t in self.tasks):
                self.status = JobStatus.CANCELLED
            else:
                self.status = JobStatus.FAILED
            self.completed_at = _utc_now()
        elif any(t.status == TaskStatus.NEEDS_REVIEW for t in self.tasks):
            self.status = JobStatus.PAUSED
            self.completed_at = None

    def calculate_stats(self) -> Dict[str, int]:
        total = len(self.tasks)
        submitted = sum(1 for t in self.tasks if t.status == TaskStatus.SUBMITTED)
        failed = sum(1 for t in self.tasks if t.status == TaskStatus.FAILED)
        cancelled = sum(1 for t in self.tasks if t.status == TaskStatus.CANCELLED)
        running = sum(1 for t in self.tasks if t.status == TaskStatus.RUNNING)
        queued = sum(1 for t in self.tasks if t.status == TaskStatus.QUEUED)
        pending = sum(1 for t in self.tasks if t.status == TaskStatus.PENDING)
        return {
            "total": total,
            "submitted": submitted,
            "failed": failed,
            "cancelled": cancelled,
            "running": running,
            "queued": queued,
            "pending": pending,
            "waiting_email_slot": sum(t.status == TaskStatus.WAITING_EMAIL_SLOT for t in self.tasks),
            "waiting_email_code": sum(t.status == TaskStatus.WAITING_EMAIL_CODE for t in self.tasks),
            "verifying_email": sum(t.status == TaskStatus.VERIFYING_EMAIL for t in self.tasks),
            "submitting": sum(t.status == TaskStatus.SUBMITTING for t in self.tasks),
            "needs_review": sum(t.status == TaskStatus.NEEDS_REVIEW for t in self.tasks),
        }
