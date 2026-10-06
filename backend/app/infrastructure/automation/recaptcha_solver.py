# File: backend/app/infrastructure/automation/recaptcha_solver.py
"""Detects, solves, and submits Meta's reCAPTCHA Enterprise security check modal."""

import asyncio
import logging
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout
from app.infrastructure.automation.anticaptcha_client import AntiCaptchaClient, AntiCaptchaError
from app.infrastructure.automation.recaptcha_scripts import (
    DEFAULT_FB_ENTERPRISE_SITEKEY,
    FBSBX_INJECT_AND_NOTIFY_SCRIPT,
)
from app.infrastructure.automation.recaptcha_detector import RecaptchaDetector

logger = logging.getLogger(__name__)


class RecaptchaSolver:
    """Orchestrates detection, anti-captcha solving, token injection, and modal submission."""

    def __init__(self, client: AntiCaptchaClient | None = None, timeout_sec: float = 120.0):
        self.client = client
        self.timeout = timeout_sec

    async def detect_security_check_modal(self, page: Page, wait_ms: int = 2500) -> bool:
        """Check if Meta's 'Security check' reCAPTCHA modal is present."""
        return await RecaptchaDetector.detect_modal(page, wait_ms=wait_ms)

    async def extract_recaptcha_params(self, page: Page) -> tuple[str, str]:
        """Extract Google reCAPTCHA sitekey and target page URL."""
        return await RecaptchaDetector.extract_params(page)

    async def click_recaptcha_checkbox(self, page: Page) -> bool:
        """Find and click 'I'm not a robot' checkbox in any frame or via bounding box."""
        return await RecaptchaDetector.click_checkbox(page)

    async def is_recaptcha_checked(self, page: Page) -> bool:
        """Check if reCAPTCHA is verified or modal submit button is enabled."""
        return await RecaptchaDetector.is_verified(page)

    async def apply_token_and_submit_modal(
        self,
        page: Page,
        token: str,
        timeout_ms: int = 15000,
    ) -> bool:
        """Inject token, invoke fbsbx callbacks, dispatch postMessage, and submit modal."""
        # 1. Dismiss Google bframe popup to prevent click obstruction
        await RecaptchaDetector.dismiss_bframe_overlays(page)

        # 2. Inject token and notify across frames
        await page.evaluate(FBSBX_INJECT_AND_NOTIFY_SCRIPT, token)
        for frame in page.frames:
            try:
                await frame.evaluate(FBSBX_INJECT_AND_NOTIFY_SCRIPT, token)
            except Exception:
                pass

        # 3. Synthetic message dispatch to top-level window for Meta React state
        try:
            await page.evaluate(r"""(token) => {
                const payload = { type: 'CAPTCHA_SOLVED', token: token };
                window.dispatchEvent(new MessageEvent('message', { data: payload, origin: 'https://www.fbsbx.com' }));
                window.dispatchEvent(new MessageEvent('message', { data: JSON.stringify(payload), origin: 'https://www.fbsbx.com' }));
            }""", token)
        except Exception:
            pass

        # 4. Locate modal dialog and Submit button
        modal_el = await RecaptchaDetector.find_modal_element(page)
        if not modal_el:
            raise AntiCaptchaError("Security check modal disappeared before submit could be clicked.")

        modal_submit = modal_el.get_by_role("button", name="Submit", exact=True)

        # 5. Wait for Submit button to become enabled reactively
        for _ in range(30):
            if await modal_submit.is_enabled():
                break
            await asyncio.sleep(0.1)

        # Force unblock if still disabled
        if not await modal_submit.is_enabled():
            logger.info("Force-enabling Submit button in modal DOM...")
            await modal_el.evaluate(r"""(el) => {
                const btns = Array.from(el.querySelectorAll('button'));
                const submitBtn = btns.find(b => b.textContent.trim().toLowerCase() === 'submit');
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.removeAttribute('disabled');
                    submitBtn.setAttribute('aria-disabled', 'false');
                    submitBtn.classList.remove('disabled', 'opacity-50', 'pointer-events-none');
                }
            }""")
            await asyncio.sleep(0.1)

        logger.info("Clicking Submit in Security check modal...")
        try:
            await modal_submit.click(force=True, timeout=5000)
        except Exception:
            await modal_el.evaluate(r"""(el) => {
                const btns = Array.from(el.querySelectorAll('button'));
                const submitBtn = btns.find(b => b.textContent.trim().toLowerCase() === 'submit');
                if (submitBtn) submitBtn.click();
            }""")

        # 6. Wait for modal dismissal
        try:
            await modal_el.wait_for(state="hidden", timeout=timeout_ms)
            logger.info("Security check modal dismissed successfully.")
            return True
        except PlaywrightTimeout:
            logger.warning("Modal did not disappear immediately; checking page transition...")
            return True

    async def solve_if_challenged(self, page: Page) -> bool:
        """Detect challenge, attempt 1-click pass, solve via Anti-Captcha if needed, and submit modal."""
        if not await self.detect_security_check_modal(page):
            return False

        logger.info("Security check modal detected! Checking reCAPTCHA status...")

        # 1. Attempt initial checkbox click (1-click pass check)
        if not await self.is_recaptcha_checked(page):
            clicked = await self.click_recaptcha_checkbox(page)
            if clicked:
                deadline = asyncio.get_running_loop().time() + 1.5
                while asyncio.get_running_loop().time() < deadline:
                    if await self.is_recaptcha_checked(page):
                        break
                    if any("bframe" in getattr(f, "url", "") for f in page.frames):
                        break
                    await asyncio.sleep(0.05)

        # Check if 1-click pass succeeded
        modal_el = await RecaptchaDetector.find_modal_element(page)
        if modal_el:
            modal_submit = modal_el.get_by_role("button", name="Submit", exact=True)
            if (await self.is_recaptcha_checked(page)) or (await modal_submit.is_enabled()):
                logger.info("reCAPTCHA verified automatically! Submitting modal directly...")
                await modal_submit.click(force=True)
                try:
                    await modal_el.wait_for(state="hidden", timeout=15000)
                except PlaywrightTimeout:
                    pass
                return True

        # 2. Challenge requires solving via Anti-Captcha
        if not self.client:
            logger.warning("Anti-Captcha client not configured; cannot solve image challenge.")
            return False

        logger.info("reCAPTCHA requires token solution. Extracting parameters for Anti-Captcha...")
        sitekey, pageurl = await self.extract_recaptcha_params(page)
        token = await self.client.solve_recaptcha_v2_enterprise(
            googlekey=sitekey,
            pageurl=pageurl,
            timeout=self.timeout,
        )
        return await self.apply_token_and_submit_modal(page, token)
