# File: backend/app/application/task_admission_operation.py
"""Finite admission owner; commit uncertainty never opens the provider gate."""
import hashlib
import json
from uuid import uuid4

from app.application.task_runtime_records import CommitResolution, StartOutcomeUnknownError
from app.application.task_records import StartTaskCommand
from app.domain.exceptions.domain_exceptions import EntityNotFoundError, InvalidStateTransitionError
from app.domain.exceptions.task_errors import IdempotencyConflictError, LegacyCommandUnverifiedError, StaleVersionError, TaskBusyError
from app.domain.value_objects.enums import TaskStatus
from app.domain.value_objects.task_execution import ExecutionGrant, ExecutionScope, CurrentStartReceiptRecord


def start_fingerprint(command):
    payload = {"contract_version": 2, "kind": "START_TASK", "task_id": str(command.task_id),
               "expected_version": command.expected_version}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def check_replay(receipt, command):
    if receipt.authority_contract_version != 2:
        raise LegacyCommandUnverifiedError("LEGACY_COMMAND_UNVERIFIED")
    if (receipt.task_id != command.task_id
            or receipt.payload_fingerprint != start_fingerprint(command)):
        raise IdempotencyConflictError("COMMAND_REUSE_CONFLICT")


class TaskAdmissionOperation:
    def __init__(self, factory, runtime, authority, clock, runtime_epoch):
        self._factory, self._runtime, self._authority = factory, runtime, authority
        self._clock, self._epoch = clock, runtime_epoch

    async def run(self, principal, command, token):
        staged, receipt, committing = None, None, False
        try:
            async with self._factory.request(principal) as uow:
                account = await self._authority.validate_request_write(uow, principal)
                existing = await uow.start_receipts.get_owned(principal.operator_id, command.command_id)
                if existing:
                    check_replay(existing, command)
                    self._runtime.leave_unstaged(token)
                    return existing
                task = await uow.tasks.get_by_id(command.task_id)
                if task is None or task.operator_id != principal.operator_id:
                    raise EntityNotFoundError("NOT_FOUND")
                if task.version != command.expected_version:
                    raise StaleVersionError("TASK_VERSION_CONFLICT")
                if task.status != TaskStatus.DRAFT:
                    raise InvalidStateTransitionError("TASK_NOT_STARTABLE")
                slot = await uow.slot.read()
                ledger = await uow.browser_sessions.read_bootstrap_snapshot()
                if not slot.is_free or not ledger.complete or ledger.unclosed_records or ledger.total_charged:
                    raise TaskBusyError("EXECUTION_NOT_READY")
                grant = ExecutionGrant(ExecutionScope(principal.operator_id, task.id, uuid4(),
                    account.run_version, slot.generation + 1, self._epoch), command.command_id,
                    self._clock.now(), task.version)
                staged = self._runtime.stage(token, grant)
                previous_attempt = task.attempt_id
                task.admit_attempt(grant)
                await uow.slot.claim(grant, expected_generation=slot.generation)
                await uow.tasks.save(task, expected_version=command.expected_version,
                                     expected_attempt_id=previous_attempt)
                receipt = CurrentStartReceiptRecord(operator_id=principal.operator_id,
                    command_id=command.command_id, task_id=task.id, attempt_id=grant.attempt_id,
                    slot_generation=grant.slot_generation, run_version=grant.run_version,
                    runtime_epoch=self._epoch, admitted_task_version=task.version,
                    admitted_at=grant.admitted_at, payload_fingerprint=start_fingerprint(command))
                await uow.start_receipts.insert(receipt)
                committing = True
                await uow.commit()
        except BaseException:
            if staged is None:
                self._runtime.leave_unstaged(token)
                raise
            resolution = (await self.settle(principal.operator_id, command.command_id, staged)
                          if committing else CommitResolution.CONFIRMED_ABSENT)
            if resolution == CommitResolution.CONFIRMED_ABSENT:
                await self._runtime.abort_stage(staged)
                raise
            if resolution != CommitResolution.CONFIRMED_COMMIT:
                self._runtime._retain_blocked(staged, "START_OUTCOME_UNKNOWN")
                raise StartOutcomeUnknownError("START_OUTCOME_UNKNOWN") from None
        try:
            self._runtime.activate(staged)
        except Exception:
            self._runtime._retain_blocked(staged, "START_OUTCOME_UNKNOWN")
            raise StartOutcomeUnknownError("START_OUTCOME_UNKNOWN") from None
        return receipt

    async def settle(self, owner, command_id, staged):
        try:
            async with self._factory.owned(owner) as uow:
                receipt = await uow.start_receipts.get_owned(owner, command_id)
                slot = await uow.slot.read()
                task = await uow.tasks.get_by_id(staged.grant.scope.task_id)
                if receipt is None and slot.grant != staged.grant and (task is None or task.attempt_id != staged.grant.attempt_id):
                    return CommitResolution.CONFIRMED_ABSENT
                if (receipt and receipt.authority_contract_version == 2
                        and receipt.operator_id == owner and receipt.command_id == command_id
                        and receipt.task_id == staged.grant.scope.task_id
                        and receipt.attempt_id == staged.grant.attempt_id
                        and receipt.slot_generation == staged.grant.slot_generation
                        and receipt.runtime_epoch == staged.grant.runtime_epoch
                        and receipt.run_version == staged.grant.run_version
                        and receipt.admitted_task_version == staged.grant.observed_task_version + 1
                        and receipt.payload_fingerprint == start_fingerprint(StartTaskCommand(
                            command_id, staged.grant.scope.task_id, staged.grant.observed_task_version))
                        and slot.grant == staged.grant and task
                        and task.attempt_id == staged.grant.attempt_id
                        and task.last_start_command_id == staged.grant.command_id
                        and task.run_version == staged.grant.run_version
                        and task.version == receipt.admitted_task_version):
                    return CommitResolution.CONFIRMED_COMMIT
        except Exception:
            return CommitResolution.UNKNOWN
        return CommitResolution.UNKNOWN


