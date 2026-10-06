# File: backend/app/infrastructure/persistence/mappers.py
from uuid import UUID
from app.domain.entities.batch_job import BatchJob
from app.domain.entities.owner_profile import OwnerProfile
from app.domain.entities.proxy_item import ProxyItem
from app.domain.entities.report_task import ReportTask
from app.domain.value_objects.email_address import EmailAddress
from app.domain.value_objects.enums import OwnerRole, JobStatus, PlatformType, ProxyCountry, ProxyStatus, TaskStatus
from app.domain.value_objects.explanation import ExplanationText
from app.domain.value_objects.original_url import OriginalUrl
from app.domain.value_objects.target_url import TargetUrl
from app.infrastructure.persistence.models import (
    BatchJobModel,
    OwnerProfileModel,
    ProxyModel,
    ReportTaskModel,
)


class DataMapper:
    @staticmethod
    def profile_to_domain(m: OwnerProfileModel) -> OwnerProfile:
        return OwnerProfile(
            id=UUID(m.id),
            full_name=m.full_name,
            email=EmailAddress.from_string(m.email),
            country=m.country,
            rights_owner_name=m.rights_owner_name,
            sender_name=m.sender_name,
            rights_jurisdiction=m.rights_jurisdiction,
            owner_role=OwnerRole(m.owner_role) if m.owner_role else None,
            organization_name=m.organization_name or "",
            created_at=m.created_at,
        )

    @staticmethod
    def profile_to_model(e: OwnerProfile) -> OwnerProfileModel:
        return OwnerProfileModel(
            id=str(e.id),
            full_name=e.full_name,
            email=e.email.value,
            country=e.country,
            rights_owner_name=e.rights_owner_name,
            sender_name=e.sender_name,
            rights_jurisdiction=e.rights_jurisdiction,
            owner_role=e.owner_role.value if e.owner_role else None,
            organization_name=e.organization_name,
            created_at=e.created_at,
        )

    @staticmethod
    def proxy_to_domain(m: ProxyModel) -> ProxyItem:
        return ProxyItem(
            id=UUID(m.id),
            protocol=m.protocol,
            host=m.host,
            port=m.port,
            country=ProxyCountry(m.country),
            username=m.username,
            password=m.password,
            status=ProxyStatus(m.status),
            latency_ms=m.latency_ms,
            consecutive_failures=m.consecutive_failures,
            created_at=m.created_at,
            last_checked_at=m.last_checked_at,
        )

    @staticmethod
    def proxy_to_model(e: ProxyItem) -> ProxyModel:
        return ProxyModel(
            id=str(e.id),
            protocol=e.protocol,
            host=e.host,
            port=e.port,
            country=e.country.value,
            username=e.username,
            password=e.password,
            status=e.status.value,
            latency_ms=e.latency_ms,
            consecutive_failures=e.consecutive_failures,
            created_at=e.created_at,
            last_checked_at=e.last_checked_at,
        )

    @staticmethod
    def task_to_domain(m: ReportTaskModel) -> ReportTask:
        return ReportTask(
            id=UUID(m.id),
            batch_job_id=UUID(m.batch_job_id),
            target_url=TargetUrl(
                url=m.target_url,
                platform=PlatformType(m.target_platform),
                content_type=m.target_content_type,
            ),
            original_url=OriginalUrl(url=m.original_url),
            explanation=ExplanationText(content=m.explanation),
            status=TaskStatus(m.status),
            retry_count=m.retry_count,
            max_retries=m.max_retries,
            proxy_id=UUID(m.proxy_id) if m.proxy_id else None,
            meta_case_number=m.meta_case_number,
            screenshot_path=m.screenshot_path,
            error_message=m.error_message,
            infringing_account=m.infringing_account,
            attempt_id=m.attempt_id,
            input_snapshot=m.input_snapshot or {},
            verification=m.verification or {},
            submitted_at=m.submitted_at,
            receipt_text=m.receipt_text,
            created_at=m.created_at,
            completed_at=m.completed_at,
        )

    @staticmethod
    def task_to_model(e: ReportTask) -> ReportTaskModel:
        return ReportTaskModel(
            id=str(e.id),
            batch_job_id=str(e.batch_job_id),
            target_url=e.target_url.url,
            target_platform=e.target_url.platform.value,
            target_content_type=e.target_url.content_type,
            original_url=e.original_url.url,
            explanation=e.explanation.content,
            status=e.status.value,
            retry_count=e.retry_count,
            max_retries=e.max_retries,
            proxy_id=str(e.proxy_id) if e.proxy_id else None,
            meta_case_number=e.meta_case_number,
            screenshot_path=e.screenshot_path,
            error_message=e.error_message,
            infringing_account=e.infringing_account,
            attempt_id=e.attempt_id,
            input_snapshot=e.input_snapshot,
            verification=e.verification,
            submitted_at=e.submitted_at,
            receipt_text=e.receipt_text,
            created_at=e.created_at,
            completed_at=e.completed_at,
        )

    @staticmethod
    def job_to_domain(m: BatchJobModel) -> BatchJob:
        job = BatchJob(
            id=UUID(m.id),
            name=m.name,
            owner_profile_id=UUID(m.owner_profile_id),
            preferred_country=ProxyCountry(m.preferred_country) if m.preferred_country else None,
            concurrency=m.concurrency,
            delay_min=m.delay_min,
            delay_max=m.delay_max,
            status=JobStatus(m.status),
            created_at=m.created_at,
            completed_at=m.completed_at,
            tasks=[DataMapper.task_to_domain(t) for t in (m.tasks or [])],
        )
        return job

    @staticmethod
    def job_to_model(e: BatchJob) -> BatchJobModel:
        return BatchJobModel(
            id=str(e.id),
            name=e.name,
            owner_profile_id=str(e.owner_profile_id),
            preferred_country=e.preferred_country.value if e.preferred_country else None,
            concurrency=e.concurrency,
            delay_min=e.delay_min,
            delay_max=e.delay_max,
            status=e.status.value,
            created_at=e.created_at,
            completed_at=e.completed_at,
        )
