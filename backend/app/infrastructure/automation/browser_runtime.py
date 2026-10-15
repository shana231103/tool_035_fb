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
    if getattr(error, "code", None):
        from app.domain.exceptions.browser_errors import safe_browser_reason
        return safe_browser_reason(error.code)
    return "BROWSER_CONTEXT_FAILED"


def browser_failure_message(error: Exception) -> str:
    reason = browser_failure_reason(error)
    if reason == "BROWSER_EVENT_LOOP_UNSUPPORTED":
        return "Browser cannot start with this Windows backend runtime. Restart using backend/run_server.py, then retry the failed task."
    return f"Browser report session unavailable ({reason}). Check browser readiness before retrying."
