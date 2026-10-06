# File: backend/app/infrastructure/automation/playwright_reporter.py
import asyncio
import logging
import os
import time
from uuid import UUID
from playwright.async_api import TimeoutError as PlaywrightTimeout
from app.domain.ports.automation_driver import AutomationResult, IAutomationDriver, AutomationSubmissionParams, ProgressCallback
from app.domain.ports.email_verification import IVerificationBroker
from app.infrastructure.automation.browser_pool import BrowserPool
from app.infrastructure.automation.browser_runtime import browser_failure_message, browser_failure_reason
from app.domain.value_objects.enums import TaskStatus, PlatformType, OwnerRole
from app.domain.value_objects.target_url import TargetUrl
from app.domain.value_objects.original_url import OriginalUrl
from app.infrastructure.automation.form_selectors import MetaFormSelectors as S, FormContractError
from app.infrastructure.automation.form_diagnostics import safe_form_failure
from app.infrastructure.automation.copyright_pages import CopyrightPages
from app.infrastructure.automation.email_verification import EmailVerification
from app.infrastructure.automation.otp_dom_contract import OtpDomContract
from app.infrastructure.automation.otp_diagnostics import screenshot_with_otp_mask
from app.infrastructure.automation.submission_receipt import SubmissionReceipt
from app.infrastructure.automation.stealth_config import apply_stealth
from app.infrastructure.automation.anticaptcha_client import AntiCaptchaError
from app.infrastructure.automation.recaptcha_solver import RecaptchaSolver

logger = logging.getLogger(__name__)


class PlaywrightMetaReporter(IAutomationDriver):
    def __init__(self, browser_pool: BrowserPool, screenshots_dir: str, verification: IVerificationBroker | None = None,
                 navigation_timeout_ms: int = 45000, otp_timeout: float = 600,
                 max_code_attempts: int = 5, max_resends: int = 2, receipt_timeout_ms: int = 30000,
                 *, collector=None, otp_contract: OtpDomContract | None = None,
                 allow_test_contract: bool = False,
                 captcha_solver: RecaptchaSolver | None = None):
        self._pool, self._broker = browser_pool, verification
        self._screenshots_dir = os.path.abspath(screenshots_dir)
        self._navigation = navigation_timeout_ms
        self._otp_timeout, self._attempts, self._resends = otp_timeout, max_code_attempts, max_resends
        self._receipt_timeout = receipt_timeout_ms
        self._collector = collector
        self._otp_contract = otp_contract or OtpDomContract()
        self._allow_test_contract = allow_test_contract
        self._captcha_solver = captcha_solver
        os.makedirs(self._screenshots_dir, exist_ok=True)

    async def submit_copyright_report(self, params: AutomationSubmissionParams,
                                      progress: ProgressCallback | None = None) -> AutomationResult:
        start, context, stage, submitted = time.perf_counter(), None, "validation", False
        controls = None
        try:
            UUID(params.task_id)
            UUID(params.attempt_id)
            if params.platform != "FACEBOOK" or TargetUrl.from_raw_url(params.target_url).platform != PlatformType.FACEBOOK:
                raise FormContractError("Only Facebook Copyright targets are supported.")
            OriginalUrl.from_raw_url(params.original_url)
            if OwnerRole(params.owner_role) != OwnerRole.OWNER:
                raise FormContractError("Only rights owners may submit reports.")
            if not all((params.owner_name, params.sender_name, params.rights_jurisdiction,
                        params.owner_email, params.explanation, self._broker, progress)):
                raise FormContractError("Complete profile and verification wiring are required.")
            if self._collector is None or params.mailbox_binding is None:
                raise FormContractError("A connected Microsoft mailbox is required.")
            if params.mailbox_binding.meta_email.casefold() != params.owner_email.strip().casefold():
                raise FormContractError("Mailbox mapping does not match the report email.")
            self._otp_contract.assert_usable(allow_test=self._allow_test_contract)
            await self._collector.assert_ready(params.mailbox_binding)
            stage = "context"
            context = await self._pool.get_context(params.proxy_server, params.proxy_username, params.proxy_password)
            page = await context.new_page()
            page.set_default_timeout(self._navigation)
            await apply_stealth(page)
            stage = "navigation"
            await page.goto(S.FORM_URL, timeout=self._navigation, wait_until="domcontentloaded")
            stage = "four-page form"
            controls = CopyrightPages(page, self._navigation)
            await controls.prepare(params)
            stage = "email verification"
            await EmailVerification(page, self._broker, self._otp_timeout,
                self._attempts, self._resends, self._navigation, collector=self._collector,
                contract=self._otp_contract, allow_test=self._allow_test_contract).verify(params, progress)
            await controls.errors()
            submit = await controls.required(page.get_by_role("button", name="Submit", exact=True), "Submit")
            if not await submit.is_enabled():
                raise FormContractError("Submit is disabled after verification.")
            await progress(TaskStatus.SUBMITTING, {})
            submitted = True  # Set before dispatch; a timeout cannot prove the click was not delivered.
            stage = "receipt"
            await submit.click()
            if self._captcha_solver:
                await self._captcha_solver.solve_if_challenged(page)
            receipt, case = await SubmissionReceipt(page, self._receipt_timeout).read()
            filename = f"task_{params.task_id}_{params.attempt_id}.png"
            if not await screenshot_with_otp_mask(page, os.path.join(self._screenshots_dir, filename),
                    self._otp_contract, extra_masks=[page.get_by_text(params.owner_email, exact=False)]):
                filename = None
            return AutomationResult(True, case_number=case, screenshot_path=filename,
                receipt_text=receipt, duration_seconds=time.perf_counter() - start)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if stage == "receipt":
                logger.warning("Receipt stage failed: %s", error)
            if stage == "context":
                logger.warning("Browser setup failed: reason=%s", browser_failure_reason(error))
            if isinstance(error, AntiCaptchaError):
                message = f"Security check captcha resolution failed: {error}"
            elif stage == "receipt" and isinstance(error, FormContractError):
                message = f"Receipt unconfirmed: {error}"
            else:
                message = (browser_failure_message(error) if stage == "context" else
                           safe_form_failure(error, getattr(controls, "stage", "prepare")) if stage == "four-page form" else
                           f"Form stopped at {stage}. Check the input or form DOM contract.")
            if stage == "four-page form":
                logger.warning("Form preparation failed: %s", message)
            return AutomationResult(False, needs_review=submitted,
                retryable=not submitted and stage == "navigation" and isinstance(error, PlaywrightTimeout),
                error_message=message,
                duration_seconds=time.perf_counter() - start)
        finally:
            if self._collector:
                try:
                    await self._collector.close(params.task_id, params.attempt_id)
                except Exception:
                    logger.warning("Mailbox collection cleanup failed: %s", params.task_id)
            if self._broker:
                try:
                    await self._broker.close(params.task_id)
                except Exception:
                    logger.warning("Verification cleanup failed: %s", params.task_id)
            if context:
                try:
                    await self._pool.close_context(context)
                except Exception:
                    logger.warning("Browser cleanup failed: %s", params.task_id)
