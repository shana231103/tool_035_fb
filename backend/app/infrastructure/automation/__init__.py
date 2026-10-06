# File: backend/app/infrastructure/automation/__init__.py
from app.infrastructure.automation.browser_pool import BrowserPool
from app.infrastructure.automation.form_selectors import MetaFormSelectors
from app.infrastructure.automation.playwright_reporter import PlaywrightMetaReporter
from app.infrastructure.automation.anticaptcha_client import AntiCaptchaClient, AntiCaptchaError
from app.infrastructure.automation.recaptcha_solver import RecaptchaSolver
from app.infrastructure.automation.recaptcha_detector import RecaptchaDetector
from app.infrastructure.automation.stealth_config import apply_stealth, get_random_user_agent

__all__ = [
    "BrowserPool",
    "MetaFormSelectors",
    "PlaywrightMetaReporter",
    "AntiCaptchaClient",
    "AntiCaptchaError",
    "RecaptchaSolver",
    "RecaptchaDetector",
    "apply_stealth",
    "get_random_user_agent",
]
