"""Safe browser setup diagnostics; provider errors may contain private proxy data."""
import asyncio
import sys


class BrowserRuntimeError(RuntimeError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def assert_supported_browser_loop() -> None:
    if sys.platform == "win32" and isinstance(asyncio.get_running_loop(), asyncio.SelectorEventLoop):
        raise BrowserRuntimeError("BROWSER_EVENT_LOOP_UNSUPPORTED")


def browser_failure_reason(error: Exception) -> str:
    if isinstance(error, BrowserRuntimeError):
        return error.reason if error.reason == "BROWSER_EVENT_LOOP_UNSUPPORTED" else "BROWSER_CONTEXT_FAILED"
    if "Executable doesn't exist" in str(error):
        return "BROWSER_NOT_INSTALLED"
    return "BROWSER_CONTEXT_FAILED"


def browser_failure_message(error: Exception) -> str:
    reason = browser_failure_reason(error)
    if reason == "BROWSER_EVENT_LOOP_UNSUPPORTED":
        return "Browser cannot start with this Windows backend runtime. Restart using backend/run_server.py, then retry the failed task."
    if reason == "BROWSER_NOT_INSTALLED":
        return "The automation browser is not installed. Run python -m playwright install chromium on the backend host, then retry the failed task."
    return "Browser could not create a report session. Check browser and proxy setup, then retry the failed task."
