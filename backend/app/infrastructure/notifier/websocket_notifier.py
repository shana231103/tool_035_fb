# File: backend/app/infrastructure/notifier/websocket_notifier.py
import inspect
import logging
from uuid import UUID
from typing import Any, Callable
from app.domain.ports.notifier import IEventNotifier

logger = logging.getLogger(__name__)


class WebSocketNotifier(IEventNotifier):
    """Callbacks synchronously enqueue locally, without transport awaits."""

    def __init__(self) -> None:
        self._subscribers: list[Callable[[dict[str, Any]], None]] = []

    def register_broadcast_callback(self, callback: Callable[[dict[str, Any]], None]) -> None:
        if inspect.iscoroutinefunction(callback):
            raise ValueError("Notification callbacks must synchronously enqueue.")
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unregister_broadcast_callback(self, callback: Callable[[dict[str, Any]], None]) -> None:
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def _publish(self, message: dict[str, Any]) -> None:
        for callback in list(self._subscribers):
            try:
                result = callback(message)
                if inspect.isawaitable(result):
                    if inspect.iscoroutine(result):
                        result.close()
                    raise ValueError("Notification callback returned an awaitable.")
            except Exception:
                logger.warning("Local notification enqueue failed.")

    async def broadcast_job_update(self, job_id: str, payload: dict[str, Any]) -> None:
        self._publish({"type": "JOB_UPDATE", "job_id": job_id, "data": payload})

    async def broadcast_task_update(self, job_id: str, task_id: str,
                                    payload: dict[str, Any]) -> None:
        self._publish({"type": "TASK_UPDATE", "job_id": job_id,
                       "task_id": task_id, "data": payload})

    async def broadcast_standalone_task_update(
        self,
        task_id: str,
        version: int,
        attempt_id: Any,
        payload: dict[str, Any],
        owner_id: Any = None,
    ) -> None:
        if owner_id is None or not isinstance(version, int) or isinstance(version, bool) or version < 1:
            logger.warning("Rejected unscoped task notification.")
            return
        task_id, owner_id = str(UUID(str(task_id))), str(UUID(str(owner_id)))
        attempt_id = str(UUID(str(attempt_id))) if attempt_id else None
        safe = {}
        for key in ("status", "is_running", "is_terminal", "is_retriable"):
            value = payload.get(key)
            if (key == "status" and value in {
                "DRAFT", "PREPARING", "RUNNING", "WAITING_EMAIL_CODE",
                "VERIFYING_EMAIL", "SUBMITTING", "SUBMITTED", "FAILED",
                "CANCELLED", "NEEDS_REVIEW",
            }) or (key != "status" and isinstance(value, bool)):
                safe[key] = value
        msg: dict[str, Any] = {
            "type": "TASK_UPDATE",
            "task_id": task_id,
            "version": version,
            "attempt_id": str(attempt_id) if attempt_id else None,
            "data": safe,
        }
        if owner_id:
            msg["owner_id"] = str(owner_id)
        self._publish(msg)
