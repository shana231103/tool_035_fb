# File: backend/app/infrastructure/automation/browser_pool.py
import asyncio
import logging
from typing import Any, Dict, Optional
from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright
from app.infrastructure.automation.stealth_config import get_random_user_agent
from app.infrastructure.automation.browser_runtime import assert_supported_browser_loop


logger = logging.getLogger(__name__)


async def _drain_owned_task(task: asyncio.Task[Any]) -> Any:
    """Join owned work even if the caller is cancelled again during cleanup."""
    while True:
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            if task.cancelled():
                raise


async def _stop_driver(playwright: Playwright) -> None:
    try:
        await _drain_owned_task(asyncio.create_task(playwright.stop()))
    except Exception:
        logger.warning("Playwright driver cleanup failed", exc_info=True)


class BrowserPool:
    def __init__(self, headless: bool = True):
        self._headless = headless
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._lock = asyncio.Lock()
        self._active_contexts_count = 0

    async def initialize(self) -> None:
        async with self._lock:
            if self._browser is not None:
                return
            assert_supported_browser_loop()
            start = asyncio.create_task(async_playwright().start())
            try:
                playwright = await asyncio.shield(start)
            except asyncio.CancelledError:
                # A successful start can return a driver after caller cancellation.
                # Capture that ownership before stopping it and releasing the lock.
                try:
                    playwright = await _drain_owned_task(start)
                except Exception:
                    logger.warning("Cancelled Playwright start failed", exc_info=True)
                else:
                    await _stop_driver(playwright)
                raise
            try:
                browser = await playwright.chromium.launch(
                    headless=self._headless,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-infobars",
                        "--disable-blink-features=AutomationControlled",
                        "--window-size=1920,1080",
                    ],
                )
            except BaseException:
                await _stop_driver(playwright)
                raise
            self._playwright, self._browser = playwright, browser

    async def get_context(
        self,
        proxy_server: Optional[str] = None,
        proxy_username: Optional[str] = None,
        proxy_password: Optional[str] = None,
    ) -> BrowserContext:
        if not self._browser:
            await self.initialize()

        proxy_dict: Optional[Dict[str, Any]] = None
        if proxy_server:
            proxy_dict = {"server": proxy_server}
            if proxy_username:
                proxy_dict["username"] = proxy_username
            if proxy_password:
                proxy_dict["password"] = proxy_password

        context = await self._browser.new_context(
            proxy=proxy_dict,
            user_agent=get_random_user_agent(),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York",
            ignore_https_errors=False,
        )
        self._active_contexts_count += 1
        return context

    async def close_context(self, context: BrowserContext) -> None:
        try:
            await context.close()
        finally:
            self._active_contexts_count = max(0, self._active_contexts_count - 1)

    async def shutdown(self) -> None:
        async with self._lock:
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
