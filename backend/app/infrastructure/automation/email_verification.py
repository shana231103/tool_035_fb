# File: backend/app/infrastructure/automation/email_verification.py
import asyncio
from datetime import datetime, timezone
from app.domain.ports.automation_driver import AutomationSubmissionParams, ProgressCallback
from app.domain.value_objects.enums import TaskStatus
from app.domain.value_objects.mailbox_verification import stamp_dispatch
from app.infrastructure.automation.form_selectors import FormContractError
from app.infrastructure.automation.otp_dom_contract import OtpDomContract
from app.infrastructure.automation.otp_observer import OtpObserver
from app.infrastructure.automation.meta_otp_observer import MetaOtpObserver
from app.infrastructure.automation.otp_collection_wait import collect_command


class EmailVerification:
    def __init__(self, page, broker, timeout: float = 600, max_attempts: int = 5,
                 max_resends: int = 2, timeout_ms: int = 45000, *, collector=None,
                 contract: OtpDomContract | None = None, allow_test: bool = False):
        if timeout <= 0 or max_attempts <= 0 or max_resends < 0:
            raise ValueError("Email verification limits are invalid.")
        self.page, self.broker, self.collector = page, broker, collector
        self.timeout, self.max_attempts, self.max_resends = timeout, max_attempts, max_resends
        self.contract = contract or OtpDomContract()
        if self.contract.mode == "meta_auto_fill":
            self.max_attempts, self.max_resends = 1, 0
        self.allow_test = allow_test

    async def _send(self, observer, params, deadline, *, resend=False):
        observed = await observer.inspect()
        if ((not resend and observed.state != "unsent") or
                (resend and (not observed.resend_supported or observed.state not in ("sent", "rejected")))):
            raise FormContractError("Email verification send state is unconfirmed.")
        prepared = await self.collector.prepare_send(params.mailbox_binding,
            params.task_id, params.attempt_id, deadline)
        button = await observer.required(observer.button(
            self.contract.resend_label if resend else self.contract.request_label))
        if not await button.is_enabled():
            raise FormContractError("Email verification request is disabled.")
        current = await observer.inspect()
        if current.revision != observed.revision or current.state != observed.state:
            raise FormContractError("Email verification send state changed before dispatch.")
        prepared = stamp_dispatch(prepared, datetime.now(timezone.utc))
        await button.click(timeout=max(1, (deadline - asyncio.get_running_loop().time()) * 1000))
        ack = await observer.wait_send_ack(deadline, observed.revision)
        return await self.collector.mark_dispatched(prepared, ack.request_id)

    async def verify(self, params: AutomationSubmissionParams, progress: ProgressCallback) -> None:
        if self.collector is None or params.mailbox_binding is None:
            raise FormContractError("Microsoft mailbox verification is required.")
        self.contract.assert_usable(allow_test=self.allow_test)
        observer_type = MetaOtpObserver if self.contract.mode == "meta_auto_fill" else OtpObserver
        observer = observer_type(self.page, self.contract, allow_test=self.allow_test)
        deadline = asyncio.get_running_loop().time() + self.timeout
        self._verified = False
        try:
            async with asyncio.timeout(self.timeout):
                await self._verify(observer, params, progress, deadline)
        except TimeoutError:
            raise FormContractError("Email verification timed out.") from None
        finally:
            try:
                if not self._verified:
                    await observer.clear_if_editable()
            except Exception:
                # The screenshot adapter masks the whole region when editing is impossible.
                self.page = None

    async def _verify(self, observer, params, progress, deadline):
        observed = await observer.inspect()
        if observed.state == "unsent":
            epoch = await self._send(observer, params, deadline)
            resends = 0
        elif observed.state == "sent" and observed.resend_supported and self.max_resends:
            epoch = await self._send(observer, params, deadline, resend=True)
            resends = 1
        else:
            raise FormContractError("Email verification has no confirmed send epoch.")
        attempts = 0
        while attempts < self.max_attempts:
            await self.collector.assert_current(epoch)
            observed = await observer.inspect()
            supported = observed.resend_supported and resends < self.max_resends
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise FormContractError("Email verification timed out.")
            metadata = await self.broker.open(params.task_id, params.attempt_id,
                params.owner_email, remaining, supported)
            metadata.update(attempts=attempts, resends=resends, mode="MICROSOFT_GRAPH",
                requested_at=epoch.request_started_at.isoformat(), phase="POLLING",
                last_error_code="VERIFICATION_FAILED" if attempts else None)
            await progress(TaskStatus.WAITING_EMAIL_CODE, metadata)
            command = await collect_command(self.collector, self.broker, epoch, metadata["challenge_id"])
            await self.collector.assert_current(epoch)
            await progress(TaskStatus.VERIFYING_EMAIL, {**metadata, "resend_supported": False})
            if command.kind == "resend":
                if not supported:
                    raise FormContractError("Email verification resend is unavailable.")
                epoch = await self._send(observer, params, deadline, resend=True)
                resends += 1
                await observer.clear_if_editable()
                continue
            if command.kind != "code":
                raise FormContractError("Email verification command is invalid.")
            attempt = await observer.begin_attempt(deadline)
            code = await observer.code()
            await code.fill(command.code)
            command = None
            await self.collector.assert_current(epoch)
            attempts += 1
            await observer.trigger(attempt, deadline)
            result = await observer.wait_result(attempt, deadline)
            self._verified = result.state == "verified"
            await self.collector.assert_current(epoch)
            if result.state == "verified":
                await self.broker.close(params.task_id)
                await progress(TaskStatus.RUNNING, {})
                return
            if self.contract.mode == "meta_auto_fill":
                raise FormContractError("Email verification code was rejected; a new run is required.")
            await observer.clear_if_editable()
        raise FormContractError("Email verification attempt limit reached.")
