# File: backend/app/application/use_cases/execute_report_task.py
import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4
from typing import Callable
from app.application.unit_of_work import IUnitOfWork
from app.application.task_progress import ProgressStore
from app.application.mailbox_sessions import MailboxAttemptSessions
from app.domain.ports.mailbox_code_reader import IMailboxConnections
from app.domain.exceptions.mailbox_errors import MailboxError
from app.domain.entities.owner_profile import OwnerProfile
from app.domain.entities.proxy_item import ProxyItem
from app.domain.entities.report_task import ReportTask
from app.domain.ports.automation_driver import AutomationResult, AutomationSubmissionParams, IAutomationDriver
from app.domain.ports.email_verification import IVerificationBroker
from app.domain.ports.notifier import IEventNotifier
from app.domain.value_objects.enums import TaskStatus, PlatformType
from app.domain.value_objects.explanation import ExplanationText
from app.domain.value_objects.original_url import OriginalUrl
from app.domain.value_objects.target_url import TargetUrl


class ExecuteReportTaskUseCase:
    def __init__(self, automation_driver: IAutomationDriver, notifier: IEventNotifier,
                 uow_factory: Callable[[], IUnitOfWork], verification: IVerificationBroker,
                 connections: IMailboxConnections | None = None,
                 sessions: MailboxAttemptSessions | None = None):
        self._driver = automation_driver
        self._progress = ProgressStore(uow_factory, notifier)
        self._verification = verification
        self._connections = connections
        self._sessions = sessions or MailboxAttemptSessions(connections)

    async def execute(self, task: ReportTask, profile: OwnerProfile,
                      proxy: ProxyItem | None = None) -> AutomationResult:
        profile.validate_for_submission()
        if TargetUrl.from_raw_url(task.target_url.url).platform != PlatformType.FACEBOOK:
            raise ValueError("Only Facebook Copyright tasks may run.")
        OriginalUrl.from_raw_url(task.original_url.url)
        if not self._connections:
            raise MailboxError("AUTH_REQUIRED")
        binding = await self._connections.resolve_binding(profile.email.value)
        await self._connections.assert_ready(binding)
        task.mark_running(proxy_id=proxy.id if proxy else None)
        task.attempt_id = str(uuid4())
        task.verification = {}
        explanation_content = " ".join(task.explanation.content.replace("\r\n", " ").replace("\r", " ").replace("\n", " ").split())
        if len(explanation_content) > ExplanationText.MAX_LENGTH:
            if "I am the copyright owner of the original work" in explanation_content:
                explanation_content = ExplanationText.create_standard_dmca(task.target_content_type).content
            else:
                explanation_content = explanation_content[:ExplanationText.MAX_LENGTH].rstrip()
        task.input_snapshot = {
            "owner_name": profile.rights_owner_name.strip(), "sender_name": profile.sender_name.strip(),
            "owner_email": profile.email.value, "rights_jurisdiction": profile.rights_jurisdiction,
            "owner_role": profile.owner_role.value, "target_url": task.target_url.url,
            "original_url": task.original_url.url, "explanation": explanation_content,
        }
        async def progress(status: TaskStatus, metadata: dict) -> None:
            async def persist():
                task.status = status
                task.verification = metadata if status in (
                    TaskStatus.WAITING_EMAIL_CODE, TaskStatus.VERIFYING_EMAIL) else {}
                if status == TaskStatus.SUBMITTING:
                    task.submitted_at = datetime.now(timezone.utc)
                await self._progress.persist(task)
            if status == TaskStatus.SUBMITTING:
                await self._sessions.admit_submission(str(task.id), task.attempt_id, persist)
            else:
                await self._sessions.assert_current(str(task.id), task.attempt_id, binding)
                await persist()
            await self._progress.notify(task)

        params = AutomationSubmissionParams(
            task_id=str(task.id), attempt_id=task.attempt_id, platform="FACEBOOK",
            **task.input_snapshot,
            proxy_server=proxy.get_server_url() if proxy else None,
            proxy_username=proxy.username if proxy else None,
            proxy_password=proxy.password if proxy else None,
            infringing_account=task.infringing_account,
            mailbox_binding=binding,
        )
        try:
            self._sessions.register(str(task.id), task.attempt_id, binding, asyncio.current_task())
            await self._sessions.assert_current(str(task.id), task.attempt_id, binding)
            await self._progress.save(task)
            result = await self._driver.submit_copyright_report(params, progress)
            task.verification = {}
            if result.success and result.receipt_text:
                task.mark_submitted(result.case_number, result.screenshot_path)
                task.receipt_text = result.receipt_text
            elif result.needs_review or task.status == TaskStatus.SUBMITTING:
                task.status = TaskStatus.NEEDS_REVIEW
                task.error_message = (
                    f"Submission outcome unconfirmed ({result.error_message}). Reconcile before retrying."
                    if result.error_message
                    else "Submission outcome unconfirmed. Reconcile before retrying."
                )
            else:
                task.mark_failed(result.error_message or "Submission failed before receipt.",
                                 retryable=result.retryable)
            await self._progress.save(task)
            return result
        except asyncio.CancelledError:
            reason = self._sessions.cancellation_reason(str(task.id), task.attempt_id)
            if reason and task.status not in (TaskStatus.SUBMITTING, TaskStatus.SUBMITTED):
                task.mark_failed(reason, False)
            else:
                task.cancel()
            task.verification = {}
            await self._progress.save(task)
            raise
        except Exception:
            task.mark_failed("Report execution interrupted; inspect task before retrying.", False)
            task.verification = {}
            await self._progress.save(task)
            return AutomationResult(False, needs_review=task.status == TaskStatus.NEEDS_REVIEW)
        finally:
            try:
                await self._verification.close(str(task.id))
            except Exception:
                # Cleanup cannot change a confirmed or uncertain submission.
                logging.getLogger(__name__).warning("Challenge cleanup failed: %s", task.id)
            finally:
                await self._sessions.unregister(str(task.id), task.attempt_id)
