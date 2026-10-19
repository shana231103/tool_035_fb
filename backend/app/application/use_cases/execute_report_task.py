# File: backend/app/application/use_cases/execute_report_task.py
"""Submit one immutable standalone attempt through its admitted authority."""
import asyncio

from app.application.browser_receipts import finish_owned
from app.application.task_runtime_records import ExecutionOutcome, OwnedWorkKind, SafeProgress
from app.domain.ports.automation_driver import AutomationReceipt, AutomationSubmissionParams
from app.domain.value_objects.enums import TaskStatus


class ExecuteReportTaskUseCase:
    def __init__(self, automation_driver, factory, verification, connections, sessions,
                 browser, authority):
        self._driver, self._factory, self._verification = automation_driver, factory, verification
        self._connections, self._sessions, self._browser = connections, sessions, browser
        self._authority = authority

    async def execute(self, grant, prepared, *, progress, receipt):
        if prepared.grant != grant:
            raise ValueError("EXECUTION_GRANT_MISMATCH")
        task_id, attempt_id = str(grant.scope.task_id), str(grant.attempt_id)
        binding = prepared.mailbox_binding
        self._sessions.register(task_id, attempt_id, binding, asyncio.current_task())
        try:
            await self._sessions.assert_current(task_id, attempt_id, binding)
            await self._browser.assert_ready()
            async with self._factory.execution(grant) as uow:
                await self._authority.require_run(uow, grant)
            self._authority.validate_proxy(prepared.validated_proxy)
            params = AutomationSubmissionParams(task_id=task_id, attempt_id=attempt_id,
                platform="FACEBOOK", target_url="\n".join(prepared.target_urls),
                target_urls=prepared.target_urls, original_url=prepared.original_url,
                owner_name=prepared.owner_name, owner_email=prepared.owner_email,
                sender_name=prepared.sender_name, rights_jurisdiction=prepared.rights_jurisdiction,
                owner_role=prepared.owner_role, explanation=prepared.explanation,
                proxy_server=prepared.proxy_server, proxy_username=prepared.proxy_username,
                proxy_password=prepared.proxy_password, infringing_account=prepared.infringing_account,
                mailbox_binding=binding)

            async def on_progress(status, metadata):
                if status == TaskStatus.SUBMITTING:
                    async def persist_submitting():
                        async with self._factory.execution(grant) as uow:
                            fresh = await self._authority.require_run(uow, grant)
                            await self._authority.admit_submitting(uow, grant,
                                expected_task_version=fresh.version, input_digest=prepared.input_digest)
                            await uow.commit()
                    await self._sessions.admit_submission(task_id, attempt_id, persist_submitting)
                    await progress(status, SafeProgress(stage=status.value))
                else:
                    await self._sessions.assert_current(task_id, attempt_id, binding)
                    # Raw driver metadata never crosses the durable progress boundary.
                    await progress(status, SafeProgress(stage=status.value))

            result = await self._driver.submit_copyright_report(params, on_progress, on_receipt=receipt)
            if result.success and result.receipt_text:
                evidence = AutomationReceipt(grant.scope.task_id, grant.attempt_id,
                                             result.receipt_text, result.case_number)
                await receipt(evidence)
                return ExecutionOutcome(TaskStatus.SUBMITTED, receipt=evidence,
                                        screenshot_path=result.screenshot_path)
            return ExecutionOutcome(TaskStatus.NEEDS_REVIEW if result.needs_review else TaskStatus.FAILED,
                                    "SUBMISSION_UNCONFIRMED" if result.needs_review else "EXECUTION_FAILED")
        finally:
            async def close():
                try:
                    await self._verification.close(task_id)
                finally:
                    await self._sessions.unregister(task_id, attempt_id)
            await finish_owned(close(), OwnedWorkKind.CLEANUP)
