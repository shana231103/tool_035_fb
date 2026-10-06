# File: backend/app/infrastructure/automation/otp_diagnostics.py
from app.infrastructure.automation.otp_dom_contract import OtpDomContract


async def screenshot_with_otp_mask(page, path: str, contract: OtpDomContract, *, extra_masks=()) -> bool:
    """Mask the whole scoped region, including code rendered after success."""
    try:
        region = page.locator(contract.region)
        if not contract.region or await region.count() != 1:
            return False
        await page.screenshot(path=path, full_page=True,
                              mask=[page.locator("input, textarea"), region, *extra_masks])
        return True
    except Exception:
        return False
