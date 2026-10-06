# File: backend/app/infrastructure/automation/stealth_config.py
import random
from typing import List
from playwright.async_api import Page

USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]

STEALTH_JS = """
// Overwrite the `navigator.webdriver` property to evade bot detection
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined
});

// Mock Chrome runtime
window.chrome = {
    runtime: {},
    loadTimes: function() {},
    csi: function() {},
    app: {}
};

// Overwrite the `plugins` property
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5]
});

// Overwrite the `languages` property
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en']
});
"""


def get_random_user_agent() -> str:
    return random.choice(USER_AGENTS)


async def apply_stealth(page: Page) -> None:
    try:
        from playwright_stealth import stealth_async  # type: ignore
        await stealth_async(page)
    except Exception:
        # Fallback to direct script injection
        await page.add_init_script(STEALTH_JS)
