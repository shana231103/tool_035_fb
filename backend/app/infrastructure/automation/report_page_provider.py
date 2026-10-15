# File: backend/app/infrastructure/automation/report_page_provider.py
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True)
class ReportPageLease:
    operation_id: UUID
    page: Any = field(repr=False)
    attachment: Any = field(repr=False)


class IReportPageProvider(Protocol):
    async def acquire(self, request) -> ReportPageLease: ...
    async def release(self, lease: ReportPageLease): ...
