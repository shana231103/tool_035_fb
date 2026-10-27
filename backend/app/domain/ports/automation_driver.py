# File: backend/app/domain/ports/automation_driver.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID
from typing import Optional, Awaitable, Callable
from app.domain.value_objects.enums import TaskStatus
from app.domain.value_objects.mailbox_verification import MailboxBinding

ProgressCallback = Callable[[TaskStatus, dict], Awaitable[None]]


@dataclass(frozen=True)
class AutomationReceipt:
    task_id: UUID
    attempt_id: UUID
    receipt_text: str
    case_number: str | None = None
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        object.__setattr__(self, "task_id", UUID(str(self.task_id)))
        object.__setattr__(self, "attempt_id", UUID(str(self.attempt_id)))
        if not self.receipt_text.strip() or len(self.receipt_text.encode("utf-8")) > 16384:
            raise ValueError("Invalid receipt evidence.")
        if self.case_number is not None and len(self.case_number) > 128:
            raise ValueError("Invalid receipt case number.")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() != timezone.utc.utcoffset(self.observed_at):
            raise ValueError("Receipt observation requires UTC.")


ReceiptCallback = Callable[[AutomationReceipt], Awaitable[None]]


@dataclass(frozen=True)
class AutomationSubmissionParams:
    task_id: str
    platform: str
    target_url: str
    original_url: str
    owner_name: str
    owner_email: str
    explanation: str
    proxy_server: Optional[str] = None
    proxy_username: Optional[str] = None
    proxy_password: Optional[str] = None
    infringing_account: Optional[str] = None
    sender_name: str = ""
    rights_jurisdiction: str = ""
    owner_role: str = ""
    attempt_id: str = ""
    mailbox_binding: MailboxBinding | None = None


@dataclass(frozen=True)
class AutomationResult:
    success: bool
    case_number: Optional[str] = None
    screenshot_path: Optional[str] = None
    error_message: Optional[str] = None
    duration_seconds: float = 0.0
    needs_review: bool = False
    retryable: bool = False
    receipt_text: Optional[str] = None


class IAutomationDriver(ABC):
    @abstractmethod
    async def submit_copyright_report(
        self, params: AutomationSubmissionParams, progress: ProgressCallback | None = None,
        *, on_receipt: ReceiptCallback | None = None
    ) -> AutomationResult:
        """Automates the submission of form 1523801815366035 and returns case/screenshot."""
        raise NotImplementedError
