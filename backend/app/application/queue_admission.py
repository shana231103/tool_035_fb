# File: backend/app/application/queue_admission.py
from app.domain.value_objects.enums import JobStatus, TaskStatus


def eligible_failed_tasks(job):
    in_flight = (TaskStatus.RUNNING, TaskStatus.WAITING_EMAIL_SLOT, TaskStatus.WAITING_EMAIL_CODE,
                 TaskStatus.VERIFYING_EMAIL, TaskStatus.SUBMITTING, TaskStatus.NEEDS_REVIEW)
    if job.status in (JobStatus.RUNNING, JobStatus.CANCELLED) or any(t.status in in_flight for t in job.tasks):
        raise ValueError("Resolve active or uncertain submissions before retrying this job.")
    failed = [task for task in job.tasks if task.status == TaskStatus.FAILED]
    if any(task.has_submission_evidence for task in failed):
        raise ValueError("Reconcile submission evidence on failed tasks before retrying this job.")
    eligible = [task for task in failed if task.can_retry_failed]
    if not eligible:
        raise ValueError("No failed tasks remain within the retry limit.")
    return eligible
