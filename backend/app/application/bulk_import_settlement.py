# File: backend/app/application/bulk_import_settlement.py
import asyncio
from app.application.bulk_import_models import BulkImportError


class BulkImportSettlement:
    """Own creates through caller cancellation and join them before DB shutdown."""
    def __init__(self, create_use_case, *, limit=2):
        self._create = create_use_case
        self._limit = min(2, limit)
        self._tasks = set()
        self._closed = False

    async def submit(self, command):
        if self._closed:
            raise BulkImportError("IMPORT_OUTCOME_UNKNOWN", status_code=503)
        if len(self._tasks) >= self._limit:
            raise BulkImportError("IMPORT_LIMIT_EXCEEDED", status_code=429)
        task = asyncio.create_task(self._create.execute(command))
        self._tasks.add(task)
        task.add_done_callback(self._settled)
        return await asyncio.shield(task)

    def _settled(self, task):
        self._tasks.discard(task)
        if not task.cancelled():
            task.exception()

    async def shutdown(self):
        self._closed = True
        while self._tasks:
            await asyncio.gather(*(asyncio.shield(task) for task in tuple(self._tasks)),
                                 return_exceptions=True)
