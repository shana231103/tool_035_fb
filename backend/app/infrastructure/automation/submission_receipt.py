# File: backend/app/infrastructure/automation/submission_receipt.py
import asyncio
import re
import time
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout
from app.infrastructure.automation.form_selectors import MetaFormSelectors as S, FormContractError


class SubmissionReceipt:
    def __init__(self, page: Page, timeout_ms: int = 30000):
        self.page, self.timeout = page, timeout_ms

    async def read(self) -> tuple[str, str | None]:
        confirmation_keywords = (
            "thank you",
            "the relevant teams will review your request",
            "your report has been submitted",
            "new request",
        )
        start = time.perf_counter()
        confirmed = False
        text = ""

        # Poll for rendered visible confirmation text in the body
        while (time.perf_counter() - start) * 1000 < self.timeout:
            try:
                body = self.page.locator("body")
                if await body.count() > 0:
                    text = await body.inner_text()
                    text_lower = text.lower()
                    if any(kw in text_lower for kw in confirmation_keywords):
                        confirmed = True
                        break
            except Exception:
                pass
            await asyncio.sleep(0.3)

        if not confirmed:
            raise PlaywrightTimeout(f"Confirmation receipt was not observed within {self.timeout}ms.")

        # Ensure the active input form is not still present
        try:
            target_control = self.page.get_by_label(S.TARGET, exact=True)
            if await target_control.count() > 0 and await target_control.first.is_visible():
                raise FormContractError("The report form is still visible; receipt is unconfirmed.")
        except FormContractError:
            raise
        except Exception:
            pass

        # Case extraction: search body text for Case number or Request ID
        match = re.search(r'(?:Case(?: number)?|Request ID)\s*[:#]?\s*(\d{8,18})', text, re.I)

        # Build appropriate receipt text representation
        text_lower = text.lower()
        if S.RECEIPT.lower() in text_lower:
            receipt_text = S.RECEIPT
        elif "thank you" in text_lower or "review your request" in text_lower:
            if "review your request" in text_lower:
                receipt_text = f"{S.RECEIPT_THANK_YOU} {S.RECEIPT_REVIEW_MSG}"
            else:
                receipt_text = S.RECEIPT_THANK_YOU
        else:
            receipt_text = S.RECEIPT

        return receipt_text, match.group(1) if match else None
