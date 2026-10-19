# File: backend/app/infrastructure/automation/copyright_pages.py
from collections.abc import Awaitable, Callable
from app.infrastructure.automation.form_selectors import MetaFormSelectors as S, FormContractError
from app.infrastructure.automation.form_diagnostics import normalize_stage
from app.infrastructure.automation.form_action_pacing import DelaySampler, Sleeper, FormActionPacer
from playwright.async_api import Page, Locator, TimeoutError as PlaywrightTimeout
from app.domain.ports.automation_driver import AutomationSubmissionParams


class CopyrightPages:
    def __init__(self, page: Page, timeout_ms: int = 45000, *,
                 delay_sampler: DelaySampler | None = None, sleeper: Sleeper | None = None) -> None:
        self.page, self.timeout, self.stage = page, timeout_ms, "prepare"
        self._delay_sampler, self._sleeper = delay_sampler, sleeper
        self._pacer: FormActionPacer | None = None

    async def _before_action(self, stage: str) -> None:
        self.stage = normalize_stage(stage)
        if self._pacer is not None:
            await self._pacer.before_action()

    def fail(self, reason: str) -> None:
        raise FormContractError("Required form contract was not satisfied.", stage=self.stage, reason=reason) from None

    async def required(self, locator: Locator, stage: str) -> Locator:
        self.stage = normalize_stage(stage)
        if await locator.count() > 1:
            self.fail("AMBIGUOUS")
        try:
            await locator.wait_for(state="visible", timeout=self.timeout)
        except PlaywrightTimeout:
            self.fail("MISSING" if await locator.count() == 0 else "TIMEOUT")
        if await locator.count() != 1:
            self.fail("AMBIGUOUS")
        if not await locator.is_enabled():
            self.fail("DISABLED")
        return locator

    async def errors(self, stage="validation") -> None:
        self.stage = normalize_stage(stage)
        if await self.page.locator('[aria-invalid="true"]:visible').count():
            self.fail("VALIDATION")
        alerts = self.page.locator('[role="alert"]:visible')
        for i in range(await alerts.count()):
            text = (await alerts.nth(i).inner_text()).strip().lower()
            if text and "is valid" not in text:
                self.fail("VALIDATION")

    async def next(self, marker: Locator, page_number: int = 1, *,
                   before_click: Callable[[], Awaitable[None]] | None = None) -> None:
        await self._before_action(f"page{page_number}_next")
        await self.errors(f"page{page_number}_validation")
        button = await self.required(self.page.get_by_role("button", name="Next", exact=True), f"page{page_number}_next")
        if before_click is not None:
            await before_click()
        self.stage = normalize_stage(f"page{page_number}_next")
        await button.click()
        await self.required(marker, f"page{page_number}_transition")

    async def fill(self, label: str, value: str, stage="field") -> None:
        self.stage = normalize_stage(stage)
        if not value:
            self.fail("MISSING_VALUE")
        await self._before_action(self.stage)
        control = await self.required(self.page.get_by_label(label, exact=True), self.stage)
        if not await control.is_editable():
            self.fail("DISABLED")
        await control.fill(value)
        actual = (await control.input_value()).replace("\r\n", "\n").replace("\r", "\n")
        expected = value.replace("\r\n", "\n").replace("\r", "\n")
        if actual != expected:
            self.fail("NOT_RETAINED")

    async def check(self, locator: Locator, stage: str) -> Locator:
        await self._before_action(stage)
        control = await self.required(locator, stage)
        await control.check()
        if not await control.is_checked():
            self.fail("NOT_RETAINED")
        return control

    async def prepare(self, params: AutomationSubmissionParams) -> None:
        if self._pacer is not None:
            raise RuntimeError("Form preparation is already running.")
        self.stage = "prepare"
        if params.owner_role != "OWNER":
            raise FormContractError("Only confirmed rights owners may submit.", stage=self.stage, reason="OWNER_REQUIRED")
        self._pacer = FormActionPacer(delay_sampler=self._delay_sampler, sleeper=self._sleeper)
        try:
            await self._prepare(params)
        finally:
            self._pacer = None

    async def _assert_owner_selected(self) -> None:
        role = await self.required(self.page.get_by_role("radio", name=S.OWNER_ROLE, exact=True), "owner_role")
        if not await role.is_checked():
            self.fail("NOT_RETAINED")

    async def _prepare(self, params: AutomationSubmissionParams) -> None:
        await self.check(self.page.get_by_role("radio", name=S.COPYRIGHT, exact=True), "copyright")
        await self.next(self.page.get_by_role("radio", name=S.PLATFORM, exact=True), 1)
        await self.check(self.page.get_by_role("radio", name=S.PLATFORM, exact=True), "platform")
        await self.next(self.page.get_by_role("combobox"), 2)
        # Live page 3 exposes a named listbox with exact role=option children.
        await self._before_action("jurisdiction_open")
        region = await self.required(self.page.get_by_role("combobox"), "jurisdiction_open")
        await region.click()
        await self._before_action("jurisdiction_option")
        options = await self.required(self.page.get_by_role("listbox", name=S.JURISDICTION, exact=True), "jurisdiction_list")
        option = await self.required(options.get_by_role("option", name=params.rights_jurisdiction, exact=True), "jurisdiction_option")
        await option.click()
        self.stage = "jurisdiction_retention"
        if (await region.inner_text()).strip() != params.rights_jurisdiction:
            self.fail("NOT_RETAINED")
        role = await self.check(self.page.get_by_role("radio", name=S.OWNER_ROLE, exact=True), "owner_role")
        await self.fill(S.OWNER_NAME, params.owner_name, "owner_name")
        self.stage = "owner_role"
        if not await role.is_checked():
            self.fail("NOT_RETAINED")
        await self.next(self.page.get_by_label(S.TARGET, exact=True), 3,
                        before_click=self._assert_owner_selected)
        for label, value, stage in (
            (S.TARGET, params.target_url, "target"), (S.ORIGINAL, params.original_url, "original"),
            (S.EXPLANATION, params.explanation, "explanation"), (S.SENDER, params.sender_name, "sender"),
            (S.EMAIL, params.owner_email, "email"), (S.CONFIRM_EMAIL, params.owner_email, "confirm_email"),
            (S.SIGNATURE, params.owner_name, "signature"),
        ):
            await self.fill(label, value, stage)
        court = await self.required(self.page.get_by_role("checkbox", name=S.COURT_ORDER, exact=True), "court_order")
        if await court.is_checked():
            self.fail("UNSUPPORTED")
        await self.errors("page4_validation")
