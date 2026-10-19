# File: backend/app/presentation/task_serialization.py
"""Safe canonical task projections, independent of runtime/provider objects."""

from app.domain.value_objects.task_error_codes import public_task_error_code
from app.presentation.task_dtos import (
    ControlViewDTO, ExecutionAvailabilityDTO, StartReceiptDTO,
    TaskPageDTO, TaskViewDTO,
)

_RUNNING = frozenset(("PREPARING", "RUNNING", "WAITING_EMAIL_CODE",
                      "VERIFYING_EMAIL", "SUBMITTING"))
_TERMINAL = frozenset(("SUBMITTED", "FAILED", "CANCELLED", "NEEDS_REVIEW"))


def _value(value):
    return value.value if hasattr(value, "value") else value


def task_view_to_dto(view) -> TaskViewDTO:
    status = _value(view.status)
    legacy = bool(getattr(view, "legacy_read_only", False))
    evidence = bool(getattr(view, "has_submission_evidence", False)) or any(
        getattr(view, field, None) is not None for field in (
            "submitted_at", "receipt_text", "meta_case_number", "screenshot_path",
        )
    )
    safe_error = public_task_error_code(
        status, getattr(view, "safe_error_code", None),
        has_submission_evidence=evidence,
    )
    return TaskViewDTO(
        id=view.id, operator_id=view.operator_id,
        owner_profile_id=view.owner_profile_id, name=view.name,
        original_url=view.original_url, explanation=view.explanation,
        preferred_country=_value(view.preferred_country), status=status,
        version=view.version, retry_count=view.retry_count,
        max_retries=view.max_retries, target_urls=list(view.target_urls),
        created_at=view.created_at, updated_at=view.updated_at,
        attempt_id=getattr(view, "attempt_id", None),
        submitted_at=getattr(view, "submitted_at", None),
        completed_at=getattr(view, "completed_at", None),
        receipt_text=view.receipt_text, case_number=view.meta_case_number,
        safe_error_code=safe_error, is_active=status in _RUNNING,
        is_running=status in _RUNNING, is_terminal=status in _TERMINAL,
        is_retriable=(not legacy and not evidence and status == "FAILED"
                      and bool(getattr(view, "can_retry", False))),
        is_legacy=legacy, legacy_read_only=legacy,
    )


def task_page_to_dto(page) -> TaskPageDTO:
    return TaskPageDTO(
        items=[task_view_to_dto(item) for item in page.items],
        limit=page.limit, offset=page.offset, has_more=page.has_more,
    )


def start_receipt_to_dto(receipt) -> StartReceiptDTO:
    contract = receipt.authority_contract_version
    legacy = contract == 1
    phase = _value(receipt.outcome_phase)
    return StartReceiptDTO(
        task_id=receipt.task_id, command_id=receipt.command_id,
        attempt_id=receipt.attempt_id, version=receipt.admitted_task_version,
        status="LEGACY_READ_ONLY" if legacy else phase,
        historical=legacy or receipt.is_historical,
        authority_contract_version=contract,
        legacy_outcome_phase=phase if legacy else None,
        safe_code="LEGACY_COMMAND_UNVERIFIED" if legacy else None,
    )


def control_view_to_dto(receipt) -> ControlViewDTO:
    return ControlViewDTO(
        command_id=receipt.command_id, status=_value(receipt.status),
        safe_code=receipt.result_code,
    )


def availability_to_dto(availability) -> ExecutionAvailabilityDTO:
    reason = ("READY" if availability.available else
              "RECOVERY_REQUIRED" if availability.blocking_recovery else "BUSY")
    return ExecutionAvailabilityDTO(available=availability.available, reason=reason)
