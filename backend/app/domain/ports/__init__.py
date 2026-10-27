# File: backend/app/domain/ports/__init__.py
from app.domain.ports.repositories import (
    IBatchJobRepository,
    IReportTaskRepository,
    IProxyRepository,
    IOwnerProfileRepository,
)
from app.domain.ports.automation_driver import (
    IAutomationDriver,
    AutomationSubmissionParams,
    AutomationResult,
)
from app.domain.ports.storage_service import IStorageService
from app.domain.ports.proxy_health import IProxyHealthService, ProxyCheckResult
from app.domain.ports.notifier import IEventNotifier

__all__ = [
    "IBatchJobRepository",
    "IReportTaskRepository",
    "IProxyRepository",
    "IOwnerProfileRepository",
    "IAutomationDriver",
    "AutomationSubmissionParams",
    "AutomationResult",
    "IStorageService",
    "IProxyHealthService",
    "ProxyCheckResult",
    "IEventNotifier",
]
