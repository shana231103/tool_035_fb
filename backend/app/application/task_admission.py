# File: backend/app/application/task_admission.py
"""Explicit Start/retry admission and owner-safe execution availability."""
import asyncio
from dataclasses import replace

from app.application.task_admission_operation import TaskAdmissionOperation, check_replay
from app.application.task_records import ExecutionAvailability
from app.application.task_runtime_records import OwnedWorkKind, StartOutcomeUnknownError
from app.domain.exceptions.domain_exceptions import EntityNotFoundError
from app.domain.exceptions.task_errors import StaleVersionError, TaskBusyError, TaskNotRetriableError


class TaskAdmissionService:
    def __init__(self, factory, runtime, operations, authority, clock, runtime_epoch):
        self._factory, self._runtime, self._operations = factory, runtime, operations
        self._authority, self._clock = authority, clock
        self._settlement_timeout = 10.0
        self._operation = TaskAdmissionOperation(factory, runtime, authority, clock, runtime_epoch)

    async def _read_replay(self, principal, command):
        async with self._factory.owned(principal.operator_id) as uow:
            receipt = await uow.start_receipts.get_owned(principal.operator_id, command.command_id)
        if receipt:
            check_replay(receipt, command)
            return replace(receipt, is_historical=True)
        return None

    async def start(self, principal, command):
        replay = await self._read_replay(principal, command)
        if replay:
            return replay
        try:
            token = self._runtime.try_enter()
        except TaskBusyError:
            replay = await self._read_replay(principal, command)
            if replay:
                return replay
            raise
        owner = asyncio.create_task(self._operation.run(principal, command, token))
        try:
            self._operations.register(OwnedWorkKind.ADMISSION, owner, attempt_id=None)
        except RuntimeError:
            owner.cancel()
            await asyncio.gather(owner, return_exceptions=True)
            self._runtime.leave_unstaged(token)
            raise
        if not await self._observe(owner):
            self._runtime.retain_admission(token)
            raise StartOutcomeUnknownError("START_OUTCOME_UNKNOWN")
        return owner.result()

    async def _observe(self, owner):
        done, _ = await asyncio.wait({owner}, timeout=self._settlement_timeout)
        return bool(done)

    async def prepare_retry(self, principal, command):
        async with self._factory.request(principal) as uow:
            await self._authority.validate_request_write(uow, principal)
            task = await uow.tasks.get_by_id(command.task_id)
            if task is None:
                raise EntityNotFoundError("NOT_FOUND")
            if task.version != command.expected_version:
                raise StaleVersionError("TASK_VERSION_CONFLICT")
            ledger = await uow.browser_sessions.read_bootstrap_snapshot()
            if not task.can_retry or self._runtime.is_busy or not ledger.complete or ledger.unclosed_records or ledger.total_charged:
                raise TaskNotRetriableError("TASK_NOT_RETRIABLE")
            attempt = task.attempt_id
            task.prepare_retry()
            await uow.tasks.save(task, expected_version=command.expected_version, expected_attempt_id=attempt)
            await uow.commit()
        async with self._factory.owned(principal.operator_id) as uow:
            return await uow.task_queries.get_detail(task.id)

    async def execution_status(self, principal):
        async with self._factory.owned(principal.operator_id) as uow:
            slot = await uow.slot.read()
            ledger = await uow.browser_sessions.read_bootstrap_snapshot()
        available = slot.is_free and not self._runtime.is_busy and ledger.complete and not ledger.unclosed_records and not ledger.total_charged
        return ExecutionAvailability(available=available, current_phase=slot.phase,
            generation=slot.generation, blocking_recovery=slot.recovery_id is not None)

    admit_start = start


