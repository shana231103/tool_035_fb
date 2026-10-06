# File: backend/app/infrastructure/automation/recaptcha_detector.py
"""DOM locator and inspection helpers for reCAPTCHA Enterprise dialogs."""

import asyncio
import logging
import re
from urllib.parse import parse_qs, urlparse
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout
from app.infrastructure.automation.recaptcha_scripts import (
    DEFAULT_FB_ENTERPRISE_SITEKEY,
    DISMISS_BFRAME_SCRIPT,
    EXTRACT_SITEKEY_SCRIPT,
)

logger = logging.getLogger(__name__)


class RecaptchaDetector:
    """Interrogates DOM and iframes for reCAPTCHA Enterprise modal, frames, and checkboxes."""

    @staticmethod
    async def detect_modal(page: Page, wait_ms: int = 2500) -> bool:
        """Check if Meta's 'Security check' reCAPTCHA modal is present and visible."""
        try:
            dialog = page.locator('[role="dialog"]:visible')
            for i in range(await dialog.count()):
                txt = (await dialog.nth(i).inner_text()).lower()
                if "security check" in txt or "robot" in txt or "recaptcha" in txt:
                    return True
            heading = page.get_by_role("heading", name="Security check", exact=False)
            if await heading.count() and await heading.first.is_visible():
                return True
            try:
                await page.locator('[role="dialog"]:has-text("Security check"), [role="dialog"]:visible').wait_for(
                    state="visible", timeout=wait_ms
                )
                return True
            except PlaywrightTimeout:
                return False
        except Exception as e:
            logger.debug("Error while checking for security check modal: %s", e)
            return False

    @staticmethod
    async def extract_params(page: Page) -> tuple[str, str]:
        """Extract the Google reCAPTCHA sitekey and target page URL."""
        sitekey: str | None = None
        target_pageurl = page.url

        for frame in page.frames:
            f_url = getattr(frame, "url", "")
            if "fbsbx.com/captcha/recaptcha/iframe" in f_url:
                target_pageurl = f_url
            if "recaptcha" in f_url:
                parsed = urlparse(f_url)
                qs = parse_qs(parsed.query)
                if qs.get("k"):
                    sitekey = qs["k"][0]
                    break
                elif qs.get("sitekey"):
                    sitekey = qs["sitekey"][0]
                    break

        if not sitekey:
            iframes = page.locator('iframe[src*="recaptcha"], iframe[src*="captcha"]')
            for i in range(await iframes.count()):
                src = await iframes.nth(i).get_attribute("src") or ""
                if "fbsbx.com/captcha/recaptcha/iframe" in src:
                    target_pageurl = src
                match = re.search(r"[?&](?:k|sitekey)=([A-Za-z0-9_-]+)", src)
                if match:
                    sitekey = match.group(1)
                    break

        if not sitekey:
            try:
                cfg = await page.evaluate(EXTRACT_SITEKEY_SCRIPT)
                sitekey = cfg.get("sitekey")
            except Exception:
                pass

        if not sitekey:
            logger.warning("Falling back to default Meta Enterprise sitekey: %s", DEFAULT_FB_ENTERPRISE_SITEKEY)
            sitekey = DEFAULT_FB_ENTERPRISE_SITEKEY

        return sitekey, target_pageurl

    @staticmethod
    async def click_checkbox(page: Page, timeout_ms: int = 2000) -> bool:
        """Rapidly click 'I'm not a robot' checkbox within ~1-2 seconds."""
        deadline = asyncio.get_running_loop().time() + (timeout_ms / 1000.0)
        while asyncio.get_running_loop().time() < deadline:
            # 1. Fast frame search (anchor frame across all attached frames)
            for frame in page.frames:
                f_url = getattr(frame, "url", "")
                if ("anchor" in f_url or "recaptcha" in f_url) and not ("bframe" in f_url):
                    anchor = frame.locator('#recaptcha-anchor, [role="checkbox"], .recaptcha-checkbox')
                    try:
                        if await anchor.count() and await anchor.first.is_visible():
                            await anchor.first.click(force=True, timeout=500)
                            return True
                    except Exception:
                        pass

            # 2. Chained and direct frame locators
            for fl in [
                page.frame_locator('iframe[src*="fbsbx.com"]').frame_locator('iframe[title*="reCAPTCHA" i], iframe[src*="recaptcha"]'),
                page.frame_locator('iframe[title*="reCAPTCHA" i]'),
                page.frame_locator('iframe[src*="recaptcha"]'),
            ]:
                try:
                    loc = fl.locator('#recaptcha-anchor, [role="checkbox"]')
                    if await loc.count() and await loc.first.is_visible():
                        await loc.first.click(force=True, timeout=300)
                        return True
                except Exception:
                    pass

            # 3. Mouse fallback on recaptcha iframe bounding box
            try:
                iframes = page.locator('[role="dialog"] iframe, iframe[src*="fbsbx.com"], iframe[src*="recaptcha"]')
                for idx in range(await iframes.count()):
                    ifr = iframes.nth(idx)
                    box = await ifr.bounding_box()
                    if box and box["width"] >= 50 and box["height"] >= 30:
                        await page.mouse.click(box["x"] + 28, box["y"] + 38)
                        return True
            except Exception:
                pass

            await asyncio.sleep(0.05)

        return False

    @staticmethod
    async def is_verified(page: Page) -> bool:
        """Check if reCAPTCHA checkbox is checked (aria-checked=true) or modal submit is enabled."""
        for frame in page.frames:
            try:
                checked = frame.locator('#recaptcha-anchor[aria-checked="true"], .recaptcha-checkbox-checked')
                if await checked.count():
                    return True
            except Exception:
                pass

        try:
            modal = page.locator('[role="dialog"]').filter(has_text="Security check")
            if not await modal.count():
                modal = page.locator('[role="dialog"]:visible')
            if await modal.count():
                submit_btn = modal.first.get_by_role("button", name="Submit", exact=True)
                if await submit_btn.is_enabled():
                    return True
        except Exception:
            pass

        return False

    @staticmethod
    async def find_modal_element(page: Page):
        """Return the visible modal element if found, or None."""
        try:
            modal = page.locator('[role="dialog"]').filter(has_text="Security check")
            if not await modal.count():
                modal = page.locator('[role="dialog"]:visible')
            if await modal.count():
                return modal.first
        except Exception:
            pass
        return None

    @staticmethod
    async def dismiss_bframe_overlays(page: Page) -> None:
        """Dismiss Google bframe challenge popups and overlay elements on page and all frames."""
        try:
            await page.evaluate(DISMISS_BFRAME_SCRIPT)
        except Exception:
            pass
        for frame in page.frames:
            try:
                await frame.evaluate(DISMISS_BFRAME_SCRIPT)
            except Exception:
                pass
