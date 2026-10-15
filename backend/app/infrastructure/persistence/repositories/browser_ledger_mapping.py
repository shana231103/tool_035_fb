# File: backend/app/infrastructure/persistence/repositories/browser_ledger_mapping.py
from dataclasses import fields
from datetime import timezone
from uuid import UUID
from app.domain.value_objects.browser_session import BrowserSessionRecord
from app.domain.value_objects.browser_status import RuntimeBinding
from app.infrastructure.persistence.browser_session_model import BrowserSessionModel

UUID_FIELDS = {"operation_id", "installation_id", "provider_binding_id", "task_id", "attempt_id"}
TIME_FIELDS = {"created_at", "updated_at", "next_retry_at"}


def binding_value(model) -> RuntimeBinding | None:
    if model is None:
        return None
    return RuntimeBinding(UUID(model.installation_id), UUID(model.provider_binding_id),
                          model.host_binding_digest, model.schema_version)


def record_value(model: BrowserSessionModel) -> BrowserSessionRecord:
    values = {f.name: getattr(model, f.name) for f in fields(BrowserSessionRecord)}
    for name in UUID_FIELDS:
        values[name] = UUID(values[name])
    for name in TIME_FIELDS:
        value = values[name]
        if value is not None:
            values[name] = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return BrowserSessionRecord(**values)


def record_columns(record: BrowserSessionRecord) -> dict:
    values = {f.name: getattr(record, f.name) for f in fields(record)}
    for name in UUID_FIELDS:
        values[name] = str(values[name])
    for name in ("phase", "cleanup_state", "completion_evidence"):
        values[name] = values[name].value
    return values
