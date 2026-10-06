# File: backend/app/domain/value_objects/__init__.py
from app.domain.value_objects.enums import (
    TaskStatus,
    JobStatus,
    ProxyCountry,
    ProxyStatus,
    PlatformType,
    ViolationType,
)
from app.domain.value_objects.target_url import TargetUrl
from app.domain.value_objects.original_url import OriginalUrl
from app.domain.value_objects.email_address import EmailAddress
from app.domain.value_objects.explanation import ExplanationText

__all__ = [
    "TaskStatus",
    "JobStatus",
    "ProxyCountry",
    "ProxyStatus",
    "PlatformType",
    "ViolationType",
    "TargetUrl",
    "OriginalUrl",
    "EmailAddress",
    "ExplanationText",
]
