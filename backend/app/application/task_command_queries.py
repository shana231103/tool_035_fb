# File: backend/app/application/task_command_queries.py
"""Read-only owner-scoped Start reconciliation; never activates history."""
from app.domain.exceptions.domain_exceptions import EntityNotFoundError


class TaskCommandQueries:
    def __init__(self, factory):
        self._factory = factory

    async def get_start(self, principal, task_id, command_id):
        async with self._factory.owned(principal.operator_id) as uow:
            receipt = await uow.start_receipts.get_owned(principal.operator_id, command_id)
        if receipt is None or receipt.task_id != task_id:
            raise EntityNotFoundError("NOT_FOUND")
        return receipt
