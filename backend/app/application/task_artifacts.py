# File: backend/app/application/task_artifacts.py
"""Task proof archival with explicit settlement and conservative compensation."""
import asyncio
from datetime import datetime, timezone
from uuid import uuid4
from app.domain.value_objects.operator_identity import ArtifactKind, ArtifactRecord


class TaskArtifacts:
    def __init__(self, factory, storage):
        self._factory, self._storage = factory, storage
        self._owned = set()

    async def own(self, operation):
        task = asyncio.create_task(operation)
        self._owned.add(task)
        task.add_done_callback(self._settled)
        return await asyncio.shield(task)

    def _settled(self, task):
        self._owned.discard(task)
        if not task.cancelled():
            task.exception()

    async def stage(self, owner, task_id, proof):
        if proof is None:
            return None
        if self._storage is None:
            raise ValueError("Proof archival storage is not configured.")
        reference = await self._storage.save_proof_file(proof.filename, proof.content)
        return ArtifactRecord(uuid4(), owner, None, task_id, ArtifactKind.PROOF,
                              reference, datetime.now(timezone.utc))

    async def attach(self, uow, record):
        if record is not None:
            await uow.artifacts.add(record)

    async def compensate_known_absent(self, owner, task_id, record):
        if record is None:
            return
        try:
            async with self._factory.owned(owner) as uow:
                task = await uow.task_queries.get_detail(task_id)
                artifact = await uow.artifacts.get_by_key(record.storage_key, record.kind)
        except Exception:
            return  # Settlement is unknown: retain the archived blob for reconciliation.
        if task is None and artifact is None:
            try:
                await self._storage.delete_proof_file(record.storage_key)
            except Exception:
                return  # An unreferenced archived blob is safe to retain.

    async def shutdown(self, deadline=None):
        if not self._owned:
            return
        remaining = None if deadline is None else max(0, deadline - asyncio.get_running_loop().time())
        _, pending = await asyncio.wait(tuple(self._owned), timeout=remaining)
        if pending:
            raise TimeoutError("CREATE_SETTLEMENT_PENDING")
