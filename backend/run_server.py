# File: backend/run_server.py
"""Local AdsPower backend; Playwright driver is required, standalone Chromium is not."""
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path
import uvicorn

def ensure_playwright_driver():
    """Check packaged driver files without launching or downloading any browser."""
    try:
        from playwright._impl._driver import compute_driver_executable
        driver_exec, cli_js = compute_driver_executable()
        if Path(driver_exec).is_file() and Path(cli_js).is_file():
            return True
    except (ImportError, OSError):
        print("Automation driver is unavailable. Contact technical support.")
        return False
    print("Automation driver files are missing. Contact technical support.")
    return False


def _open_browser_when_ready(url: str = "http://127.0.0.1:8000"):
    time.sleep(1.5)
    try:
        webbrowser.open(url)
    except Exception:
        pass


def main():
    # Freeze support is mandatory for multiprocessing & Playwright child processes on Windows
    if getattr(sys, "frozen", False):
        import multiprocessing
        multiprocessing.freeze_support()
        work_dir = Path(sys.executable).resolve().parent
    else:
        work_dir = Path(__file__).resolve().parent

    os.chdir(work_dir)

    from app.core.config import settings
    if settings.operator_deployment_mode == "hosted" and not settings.operator_public_origin:
        raise ValueError(
            "OPERATOR_PUBLIC_ORIGIN must be configured when OPERATOR_DEPLOYMENT_MODE is 'hosted'."
        )

    # The UI uses the operator's browser; automation uses AdsPower exclusively.
    if (getattr(sys, "frozen", False) or os.getenv("LAUNCH_BROWSER", "0") == "1") and settings.operator_deployment_mode != "hosted":
        ensure_playwright_driver()
        threading.Thread(target=_open_browser_when_ready, daemon=True).start()

    from app.presentation.main import app
    uvicorn.run(app, host="127.0.0.1", port=8000,
                reload=False, workers=1, loop="asyncio", proxy_headers=False)


if __name__ == "__main__":
    main()
