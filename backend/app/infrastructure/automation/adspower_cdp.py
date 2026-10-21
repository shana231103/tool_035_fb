# File: backend/app/infrastructure/automation/adspower_cdp.py
import asyncio
from playwright.async_api import async_playwright
from app.infrastructure.automation.browser_runtime import assert_supported_browser_loop
from app.infrastructure.automation.report_page_provider import ReportPageLease
from app.infrastructure.automation.adspower_wire import AdsPowerTransportError


class AdsPowerCdp:
    def __init__(self, policy, driver_factory=None):
        self.policy = policy
        self._driver_factory = driver_factory or async_playwright
        self._driver = None
        self._leases = {}
        self._startup = None
        self._shutdown = None
        self._closing = False

    @staticmethod
    async def _drain(owner):
        cancelled = False
        while not owner.done():
            try:
                await asyncio.shield(owner)
            except asyncio.CancelledError:
                cancelled = True
            except Exception:
                break
        if cancelled:
            if not owner.cancelled():
                owner.exception()
            raise asyncio.CancelledError
        return owner.result()

    async def initialize(self):
        if self._closing:
            raise AdsPowerTransportError("BROWSER_CDP_UNREACHABLE")
        if self._driver is not None:
            return
        if self._startup is None or self._startup.done():
            self._startup = asyncio.create_task(self._start_driver())
        await self._drain(self._startup)

    async def _start_driver(self):
        assert_supported_browser_loop()
        try:
            self._driver = await self._driver_factory().start()
        except Exception:
            raise AdsPowerTransportError("BROWSER_CDP_UNREACHABLE") from None

    async def attach(self, started, operation_id):
        endpoint = self.policy.endpoint(started.endpoint, started.debug_port)
        await self.initialize()
        browser = None
        try:
            async with asyncio.timeout(self.policy.settings.cdp_timeout):
                browser = await self._driver.chromium.connect_over_cdp(endpoint)
                if len(browser.contexts) != 1:
                    raise AdsPowerTransportError("BROWSER_CDP_UNREACHABLE")
                page = await browser.contexts[0].new_page()
                # Normalize the owned task tab before the reporter navigates to the form.
                await page.set_viewport_size({"width": 1280, "height": 720})
                lease = ReportPageLease(operation_id, page, browser)
                self._leases[operation_id] = lease
                return lease
        except BaseException as error:
            cancelled = isinstance(error, asyncio.CancelledError)
            if browser is not None:
                try:
                    owner = asyncio.create_task(asyncio.wait_for(browser.close(), self.policy.settings.close_timeout))
                    await self._drain(owner)
                except asyncio.CancelledError:
                    cancelled = True
                except Exception:
                    browser = None
            if cancelled:
                raise asyncio.CancelledError
            raise AdsPowerTransportError("BROWSER_CDP_UNREACHABLE") from None

    async def close_owned_page_and_disconnect(self, lease):
        owned = self._leases.get(lease.operation_id)
        if owned is not lease:
            raise AdsPowerTransportError("BROWSER_AUTHORITY_MISMATCH")
        failed = False
        for close in (lease.page.close, lease.attachment.close):
            try:
                await asyncio.wait_for(close(), self.policy.settings.close_timeout)
            except Exception:
                failed = True
        self._leases.pop(lease.operation_id, None)
        if failed:
            raise AdsPowerTransportError("BROWSER_CLEANUP_PENDING")

    async def close_operation(self, operation_id):
        lease = self._leases.get(operation_id)
        if lease is not None:
            await self.close_owned_page_and_disconnect(lease)

    async def shutdown(self):
        self._closing = True
        if self._shutdown is None:
            self._shutdown = asyncio.create_task(self._stop_driver())
        await self._drain(self._shutdown)

    async def _stop_driver(self):
        if self._startup is not None:
            try:
                await asyncio.shield(self._startup)
            except asyncio.CancelledError:
                if not self._startup.cancelled():
                    raise
                self._driver = None
            except Exception:
                self._driver = None
        for lease in tuple(self._leases.values()):
            try:
                await self.close_owned_page_and_disconnect(lease)
            except AdsPowerTransportError:
                continue
        if self._driver is not None:
            await asyncio.wait_for(self._driver.stop(), self.policy.settings.close_timeout)
            self._driver = None
