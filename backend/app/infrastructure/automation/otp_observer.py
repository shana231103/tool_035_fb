# File: backend/app/infrastructure/automation/otp_observer.py
import asyncio
from dataclasses import dataclass
from app.infrastructure.automation.form_selectors import FormContractError
from app.infrastructure.automation.otp_dom_contract import OtpDomContract


@dataclass(frozen=True)
class OtpObservation:
    state: str
    revision: int
    receptive: bool = False
    resend_supported: bool = False
    request_id: str | None = None


@dataclass(frozen=True)
class OtpAttemptObservation:
    revision: int
    prior_error_fingerprint: str | None
    trigger_kind: str
    started_at_monotonic: float


@dataclass(frozen=True)
class OtpResult:
    state: str
    revision: int
    safe_reason: str | None = None


class OtpObserver:
    def __init__(self, page, contract: OtpDomContract, *, allow_test: bool = False):
        contract.assert_usable(allow_test=allow_test)
        self.page, self.contract = page, contract
        self.region = page.locator(contract.region)

    async def required(self, locator):
        if await locator.count() != 1 or not await locator.is_visible():
            raise FormContractError("Email verification control is missing or ambiguous.")
        return locator

    def button(self, label):
        return self.region.get_by_role("button", name=label, exact=True)

    async def code(self):
        return await self.required(self.region.get_by_label(self.contract.code_label, exact=True))

    async def _visible(self, text):
        if not text:
            return False
        locator = self.region.get_by_text(text, exact=True)
        count = await locator.count()
        if count > 1:
            raise FormContractError("Email verification state is ambiguous.")
        return count == 1 and await locator.is_visible()

    async def inspect(self) -> OtpObservation:
        await self.required(self.region)
        raw = await self.region.get_attribute(self.contract.revision_attribute)
        if not raw or not raw.isdecimal():
            raise FormContractError("Email verification result freshness cannot be established.")
        code = self.region.get_by_label(self.contract.code_label, exact=True)
        receptive = (await code.count() == 1 and await code.is_visible()
                     and await code.is_editable() and await code.is_enabled())
        resend = self.button(self.contract.resend_label)
        supported = (bool(self.contract.resend_label) and await resend.count() == 1
                     and await resend.is_visible() and await resend.is_enabled())
        states = [(state, await self._visible(text)) for state, text in (
            ("verified", self.contract.verified_text), ("rejected", self.contract.rejected_text),
            ("verifying", self.contract.verifying_text), ("sent", self.contract.sent_text))]
        active = [state for state, visible in states if visible]
        if len(active) > 1:
            return OtpObservation("unknown", int(raw), receptive, supported)
        request = self.button(self.contract.request_label)
        unsent = (await request.count() == 1 and await request.is_visible()
                  and await request.is_enabled())
        state = active[0] if active else "unsent" if unsent else "unknown"
        return OtpObservation(state, int(raw), receptive, supported,
                              await self.region.get_attribute("data-request-id"))

    async def wait_send_ack(self, deadline: float, prior_revision: int) -> OtpObservation:
        while asyncio.get_running_loop().time() < deadline:
            observed = await self.inspect()
            if observed.revision > prior_revision and observed.state == "sent" and observed.receptive:
                return observed
            await asyncio.sleep(min(0.05, max(0, deadline - asyncio.get_running_loop().time())))
        raise FormContractError("Email verification send acknowledgement is unconfirmed.")

    async def begin_attempt(self, deadline: float) -> OtpAttemptObservation:
        observed = await self.inspect()
        if not observed.receptive or observed.state not in ("sent", "rejected"):
            raise FormContractError("Email verification input is not receptive.")
        if asyncio.get_running_loop().time() >= deadline:
            raise FormContractError("Email verification timed out.")
        return OtpAttemptObservation(observed.revision,
            str(observed.revision) if observed.state == "rejected" else None,
            "explicit_button", asyncio.get_running_loop().time())

    async def trigger(self, attempt: OtpAttemptObservation, deadline: float) -> None:
        if attempt.trigger_kind != "explicit_button" or asyncio.get_running_loop().time() >= deadline:
            raise FormContractError("Email verification trigger is unconfirmed.")
        current = await self.inspect()
        if current.revision != attempt.revision or not current.receptive:
            raise FormContractError("Email verification state changed before trigger.")
        control = await self.required(self.button(self.contract.verify_label))
        if not await control.is_enabled():
            raise FormContractError("Email verification trigger is disabled.")
        await control.click(timeout=max(1, (deadline - asyncio.get_running_loop().time()) * 1000))

    async def wait_result(self, attempt: OtpAttemptObservation, deadline: float) -> OtpResult:
        while asyncio.get_running_loop().time() < deadline:
            observed = await self.inspect()
            if observed.revision > attempt.revision and observed.state in ("verified", "rejected"):
                return OtpResult(observed.state, observed.revision)
            await asyncio.sleep(min(0.05, max(0, deadline - asyncio.get_running_loop().time())))
        raise FormContractError("Email verification result is unknown.")

    async def clear_if_editable(self) -> None:
        code = self.region.get_by_label(self.contract.code_label, exact=True)
        if (await code.count() == 1 and await code.is_visible()
                and await code.is_editable() and await code.is_enabled()):
            await code.fill("")
