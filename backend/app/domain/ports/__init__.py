# File: backend/app/domain/ports/__init__.py
from app.domain.ports.repositories import (
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
from app.domain.ports.task_execution_ports import (
    ITaskExecutionRepository,
    ITaskStartReceiptRepository,
    IControlRepository,
)

__all__ = [
    "IReportTaskRepository",
    "ITaskExecutionRepository",
    "ITaskStartReceiptRepository",
    "IControlRepository",
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
