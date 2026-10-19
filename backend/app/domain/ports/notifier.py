# File: backend/app/domain/ports/notifier.py
from abc import ABC, abstractmethod
from typing import Any, Dict


class IEventNotifier(ABC):
    """Best-effort local enqueue; completion never promises remote delivery.

    Implementations must keep socket I/O out of the caller's persistence/control
    path. Ordinary delivery errors cannot roll back durable state; cancellation
    remains observable by the caller.
    """
    @abstractmethod
    async def broadcast_job_update(self, job_id: str, payload: Dict[str, Any]) -> None:
        """Broadcasts batch job status change or aggregated progress metrics."""
        raise NotImplementedError

    @abstractmethod
    async def broadcast_task_update(
        self, job_id: str, task_id: str, payload: Dict[str, Any]
    ) -> None:
        """Broadcasts single task state change, log line, or submission result."""
        raise NotImplementedError

    @abstractmethod
    async def broadcast_standalone_task_update(
        self,
        task_id: str,
        version: int,
        attempt_id: Any,
        payload: Dict[str, Any],
        owner_id: Any = None,
    ) -> None:
        """Broadcasts standalone task state change or progress update."""
        raise NotImplementedError
