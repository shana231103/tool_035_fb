# File: backend/app/infrastructure/automation/meta_otp_observer.py
import asyncio
from app.infrastructure.automation.form_selectors import FormContractError
from app.infrastructure.automation.meta_otp_observer_geometry import CODE_FIELD_EVIDENCE
from app.infrastructure.automation.otp_observer import (
    OtpObserver, OtpObservation, OtpAttemptObservation, OtpResult)


class MetaOtpObserver(OtpObserver):
    """Auto-verification with local observation sequence, never a provider revision/ID."""
    def __init__(self, page, contract, *, allow_test=False):
        super().__init__(page, contract, allow_test=allow_test)
        self._fingerprint, self._revision, self._attempt, self._control = None, 0, None, None
        self._scoped = False

    async def code(self):
        label = self.region.get_by_label(self.contract.code_label, exact=True)
        if await label.count():
            return await self.required(label)
        return await self.required(self.region.get_by_placeholder(self.contract.code_label, exact=True))

    async def _scope(self):
        await self.required(self.region)
        if self._scoped:
            return
        request = await self.required(self.button(self.contract.request_label))
        forms = request.locator("xpath=ancestor::form")
        if await forms.count() > 1:
            raise FormContractError("Email verification form is ambiguous.")
        if await forms.count() == 1:
            self.region = forms
        self._scoped = True

    async def inspect(self):
        await self._scope()
        request = await self.required(self.button(self.contract.request_label))
        available = await request.is_enabled()
        sent, rejected = await self._visible(self.contract.sent_text), await self._visible(self.contract.rejected_text)
        labelled = self.region.get_by_label(self.contract.code_label, exact=True)
        candidate = labelled if await labelled.count() else self.region.get_by_placeholder(self.contract.code_label, exact=True)
        if await candidate.count() > 1:
            raise FormContractError("Email verification input is ambiguous.")
        receptive, locked, positive = False, False, False
        if await candidate.count() == 1 and await candidate.is_visible():
            code = await self.code()
            if self._control is not None and not await code.evaluate("(node, prior) => node === prior", self._control):
                raise FormContractError("Email verification input changed during verification.")
            field = await code.evaluate(CODE_FIELD_EVIDENCE)
            receptive = await code.is_editable() and await code.is_enabled()
            locked, positive = field["locked"], field["positive"]
        state = "unknown"
        if positive and sent and not available and not rejected:
            state = "verified"
        elif rejected and receptive and sent and not available and not positive:
            state = "rejected"
        elif sent and receptive and not available and not rejected and not positive:
            state = "sent"
        elif available and not sent and not rejected and not positive and not locked:
            state = "unsent"
        fingerprint = (state, receptive, locked, positive, available, sent, rejected)
        if fingerprint != self._fingerprint:
            self._revision += 1
            self._fingerprint = fingerprint
        return OtpObservation(state, self._revision, receptive, False, None)

    async def begin_attempt(self, deadline):
        observed = await self.inspect()
        if self._attempt is not None or observed.state != "sent" or not observed.receptive:
            raise FormContractError("Email verification input is not receptive for a fresh attempt.")
        if asyncio.get_running_loop().time() >= deadline:
            raise FormContractError("Email verification timed out.")
        self._control = await (await self.code()).element_handle()
        self._attempt = OtpAttemptObservation(observed.revision, None, "auto_fill",
            asyncio.get_running_loop().time())
        return self._attempt

    async def trigger(self, attempt, deadline):
        # Filling the field already triggers Meta verification; there is no Verify click.
        if attempt is not self._attempt or attempt.trigger_kind != "auto_fill" or asyncio.get_running_loop().time() >= deadline:
            raise FormContractError("Email verification trigger is unconfirmed.")

    async def wait_result(self, attempt, deadline):
        if attempt is not self._attempt:
            raise FormContractError("Email verification attempt is unconfirmed.")
        while asyncio.get_running_loop().time() < deadline:
            observed = await self.inspect()
            if observed.revision > attempt.revision and observed.state in ("verified", "rejected"):
                return OtpResult(observed.state, observed.revision)
            await asyncio.sleep(min(.05, max(0, deadline-asyncio.get_running_loop().time())))
        raise FormContractError("Email verification result is unknown.")

    async def clear_if_editable(self):
        try:
            code = await self.code()
        except FormContractError:
            return
        if await code.is_editable() and await code.is_enabled():
            await code.fill("")
