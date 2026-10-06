# File: backend/app/infrastructure/automation/anticaptcha_client.py
import asyncio
import logging
from typing import Any
import httpx

logger = logging.getLogger(__name__)


class AntiCaptchaError(Exception):
    """Exception raised for errors during Anti-Captcha API operations."""
    pass


class AntiCaptchaClient:
    """Async client for interacting with anticaptcha.top API."""

    IN_URL = "https://anticaptcha.top/in.php"
    RES_URL = "https://anticaptcha.top/res.php"
    BALANCE_URL = "https://anticaptcha.top/api/getbalance"
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(self, api_key: str, timeout: float = 30.0):
        if not api_key:
            raise ValueError("Anti-Captcha API key is required.")
        self.api_key = api_key.strip()
        self.timeout = timeout
        self._headers = {
            "Content-Type": "application/json",
            "User-Agent": self.DEFAULT_USER_AGENT,
        }

    async def get_balance(self) -> float:
        """Fetch current account balance."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.BALANCE_URL}?apikey={self.api_key}",
                headers={"User-Agent": self.DEFAULT_USER_AGENT},
            )
            if resp.status_code != 200:
                raise AntiCaptchaError(f"Balance check failed with HTTP {resp.status_code}: {resp.text}")
            data = resp.json()
            if not data.get("success"):
                raise AntiCaptchaError(f"Balance check returned error: {data.get('message', 'Unknown error')}")
            return float(data.get("balance", 0.0))

    async def create_recaptcha_v2_enterprise_task(
        self,
        googlekey: str,
        pageurl: str,
        proxy: str | None = None,
    ) -> str:
        """Submit a reCAPTCHA V2 Enterprise task and return the task ID."""
        payload: dict[str, Any] = {
            "key": self.api_key,
            "method": "userrecaptcha",
            "googlekey": googlekey,
            "pageurl": pageurl,
            "enterprise": 1,
            "json": 1,
        }
        if proxy:
            payload["proxy"] = proxy

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(self.IN_URL, json=payload, headers=self._headers)
            if resp.status_code != 200:
                raise AntiCaptchaError(f"Task submission failed with HTTP {resp.status_code}: {resp.text}")
            data = resp.json()
            if data.get("status") != 1:
                error_msg = data.get("request", "Task creation rejected by Anti-Captcha.")
                raise AntiCaptchaError(f"Anti-Captcha task creation failed: {error_msg}")
            task_id = str(data.get("request"))
            logger.info("Anti-Captcha task created successfully: task_id=%s", task_id)
            return task_id

    async def poll_task_result(
        self,
        task_id: str,
        timeout: float = 120.0,
        poll_interval: float = 3.0,
    ) -> str:
        """Poll the result of a submitted task until ready or timeout."""
        start = asyncio.get_running_loop().time()
        deadline = start + timeout
        url = f"{self.RES_URL}?key={self.api_key}&id={task_id}&json=1"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            while asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(poll_interval)
                resp = await client.get(url, headers={"User-Agent": self.DEFAULT_USER_AGENT})
                if resp.status_code != 200:
                    logger.warning("Anti-Captcha poll returned HTTP %s: %s", resp.status_code, resp.text)
                    continue
                try:
                    data = resp.json()
                except Exception as e:
                    logger.warning("Anti-Captcha response JSON parse failed: %s", e)
                    continue

                status = data.get("status")
                request_val = data.get("request", "")

                if status == 1:
                    logger.info(
                        "Anti-Captcha task %s solved successfully in %.1fs",
                        task_id,
                        asyncio.get_running_loop().time() - start,
                    )
                    return str(request_val)
                elif request_val == "CAPCHA_NOT_READY":
                    logger.debug("Anti-Captcha task %s not ready, waiting...", task_id)
                    continue
                else:
                    raise AntiCaptchaError(f"Anti-Captcha solving failed: {request_val}")

        raise AntiCaptchaError(f"Anti-Captcha solving timed out after {timeout:.1f}s (task_id={task_id}).")

    async def solve_recaptcha_v2_enterprise(
        self,
        googlekey: str,
        pageurl: str,
        timeout: float = 120.0,
        proxy: str | None = None,
    ) -> str:
        """Helper to create and poll for a reCAPTCHA V2 Enterprise token."""
        task_id = await self.create_recaptcha_v2_enterprise_task(
            googlekey=googlekey,
            pageurl=pageurl,
            proxy=proxy,
        )
        return await self.poll_task_result(task_id, timeout=timeout)
