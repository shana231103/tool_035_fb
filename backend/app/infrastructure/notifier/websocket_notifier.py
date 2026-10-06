# File: backend/app/infrastructure/notifier/websocket_notifier.py
import inspect
import logging
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
