# File: backend/app/domain/entities/__init__.py
from app.domain.entities.owner_profile import OwnerProfile
from app.domain.entities.proxy_item import ProxyItem
from app.domain.entities.report_task import ReportTask

__all__ = [
    "OwnerProfile",
    "ProxyItem",
    "ReportTask",
]
