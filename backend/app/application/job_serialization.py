# File: backend/app/application/job_serialization.py
from app.application.dtos.job_dtos import BatchJobResponseDTO, ReportTaskResponseDTO
from app.domain.entities.batch_job import BatchJob
from app.domain.entities.report_task import ReportTask
from app.application.dtos.verification_dtos import safe_verification_metadata


def task_to_dto(task: ReportTask) -> ReportTaskResponseDTO:
    fields = {name: getattr(task, name) for name in (
        'id', 'batch_job_id', 'status', 'retry_count', 'max_retries', 'proxy_id', 'meta_case_number',
        'screenshot_path', 'error_message', 'infringing_account', 'created_at',
        'completed_at', 'attempt_id', 'verification', 'submitted_at', 'receipt_text')}
    fields['verification'] = safe_verification_metadata(fields['verification'])
    return ReportTaskResponseDTO(**fields, target_url=task.target_url.url,
        target_platform=task.target_url.platform.value,
        target_content_type=task.target_url.content_type, original_url=task.original_url.url)


def job_to_dto(job: BatchJob) -> BatchJobResponseDTO:
    fields = {name: getattr(job, name) for name in (
        'id', 'name', 'owner_profile_id', 'preferred_country', 'concurrency',
        'delay_min', 'delay_max', 'status', 'created_at', 'completed_at')}
    return BatchJobResponseDTO(**fields, stats=job.calculate_stats(),
                              tasks=[task_to_dto(task) for task in job.tasks])
