# File: backend/app/application/operator_controls.py
"""Durable controls admitted before cancellation and completed only after drain."""
import asyncio
import hashlib
import json
from typing import Awaitable, Callable

from app.application.task_runtime_records import OwnedWorkKind
from app.domain.exceptions.domain_exceptions import EntityNotFoundError
from app.domain.exceptions.task_errors import IdempotencyConflictError, StaleVersionError
from app.domain.value_objects.enums import TaskStatus
from app.domain.value_objects.operator_identity import ControlTargetKind, OperatorPrincipal
from app.domain.value_objects.task_execution import ControlReceipt, ControlReceiptStatus

DisconnectFlow = Callable[[OperatorPrincipal, str], Awaitable[None]]


def fingerprint(kind, target, version, attempt):
    return hashlib.sha256(json.dumps([kind.value, str(target), version,
        str(attempt) if attempt else None], separators=(",", ":")).encode()).hexdigest()


class OperatorControlService:
    def __init__(self, factory, runtime, connections, operations, authority, clock,
                 *, disconnect_flow: DisconnectFlow | None = None):
        self._factory, self._runtime, self._connections = factory, runtime, connections
        self._operations, self._authority, self._clock = operations, authority, clock
        self._lock = asyncio.Lock()
        self._closed = False
        self._disconnect_flow = disconnect_flow

    async def stop_task(self, principal, command):
        return await self._own(self._stop_settled(principal, command))

    async def _stop_settled(self, principal, command):
        try:
            return await self._stop(principal, command)
        except Exception:
            # The writer has exited. A durable receipt authorizes only owned reconciliation.
            async with self._factory.owned(principal.operator_id) as uow:
                receipt = await uow.controls.get_owned(principal.operator_id, command.command_id)
            if receipt is None:
                raise
            if receipt.payload_fingerprint != fingerprint(ControlTargetKind.STOP_TASK,
                    command.task_id, command.expected_version, command.attempt_id):
                raise IdempotencyConflictError("COMMAND_REUSE_CONFLICT") from None
            if receipt.status == ControlReceiptStatus.ADMITTED:
                async with self._factory.operator(principal.operator_id, write=True) as uow:
                    await uow.controls.mark_uncertain(principal.operator_id, command.command_id,
                        expected_version=receipt.version, reason="CONTROL_OUTCOME_UNKNOWN")
                    await uow.commit()
            return await self.get_owned(principal, command.command_id)

    async def _own(self, operation):
        if self._closed:
            operation.close()
            raise ValueError("EXECUTION_UNAVAILABLE")
        owner = asyncio.create_task(operation)
        try:
            self._operations.register(OwnedWorkKind.CONTROL, owner, attempt_id=None)
        except RuntimeError:
            owner.cancel()
            await asyncio.gather(owner, return_exceptions=True)
            raise
        done, _ = await asyncio.wait({owner}, timeout=10)
        if not done:
            raise ValueError("CONTROL_OUTCOME_UNKNOWN")
        return owner.result()

    async def _stop(self, principal, command):
        payload = fingerprint(ControlTargetKind.STOP_TASK, command.task_id,
                              command.expected_version, command.attempt_id)
        async with self._lock:
            async with self._factory.request(principal) as uow:
                await self._authority.validate_request_write(uow, principal)
                existing = await uow.controls.get_owned(principal.operator_id, command.command_id)
                if existing:
                    if existing.payload_fingerprint != payload:
                        raise IdempotencyConflictError("COMMAND_REUSE_CONFLICT")
                    return existing
                task = await uow.tasks.get_by_id(command.task_id)
                if task is None:
                    raise EntityNotFoundError("NOT_FOUND")
                if task.version != command.expected_version or task.attempt_id != command.attempt_id:
                    raise StaleVersionError("TASK_VERSION_CONFLICT")
                slot = await uow.slot.read()
                grant = slot.grant
                if task.status == TaskStatus.DRAFT and command.attempt_id is None:
                    grant = None
                    task.cancel()
                    await uow.tasks.save(task, expected_version=command.expected_version, expected_attempt_id=None)
                elif (grant is None or grant.scope.task_id != task.id
                      or grant.scope.operator_id != principal.operator_id or grant.attempt_id != command.attempt_id):
                    raise StaleVersionError("EXECUTION_GRANT_MISMATCH")
                receipt = ControlReceipt(command_id=command.command_id, operator_id=principal.operator_id,
                    target_kind=ControlTargetKind.STOP_TASK, target_id=str(task.id),
                    target_generation=slot.generation if grant else task.version,
                    initiating_session_id=principal.session_id, auth_version=principal.auth_version,
                    admitted_at=self._clock.now(), payload_fingerprint=payload,
                    expected_task_version=command.expected_version, attempt_id=command.attempt_id)
                await uow.controls.insert(receipt)
                await uow.commit()
            drained = grant is None or await self._runtime.stop_owned(grant)
            async with self._factory.execution(grant) if grant else self._factory.request(principal) as uow:
                if drained:
                    await uow.controls.complete(principal.operator_id, command.command_id,
                                                expected_version=receipt.version, result_code="COMPLETED")
                else:
                    await uow.controls.mark_uncertain(principal.operator_id, command.command_id,
                        expected_version=receipt.version, reason="CONTROL_DRAIN_UNKNOWN")
                await uow.commit()
            return await self.get_owned(principal, command.command_id)

    async def disconnect_mailbox(self, principal, command):
        return await self._own(self._disconnect_settled(principal, command))

    async def _disconnect_settled(self, principal, command):
        try:
            return await self._disconnect(principal, command)
        except Exception:
            async with self._factory.owned(principal.operator_id) as uow:
                receipt = await uow.controls.get_owned(principal.operator_id, command.command_id)
            if receipt is None:
                raise
            if receipt.payload_fingerprint != fingerprint(ControlTargetKind.DISCONNECT_MAILBOX,
                    command.connection_id, receipt.target_generation, None):
                raise IdempotencyConflictError("COMMAND_REUSE_CONFLICT") from None
            if receipt.status == ControlReceiptStatus.ADMITTED:
                async with self._factory.operator(principal.operator_id, write=True) as uow:
                    await uow.controls.mark_uncertain(principal.operator_id, command.command_id,
                        expected_version=receipt.version, reason="MAILBOX_DISCONNECT_UNKNOWN")
                    await uow.commit()
            return await self.get_owned(principal, command.command_id)

    async def _disconnect(self, principal, command):
        async with self._lock:
            async with self._factory.owned(principal.operator_id) as uow:
                existing = await uow.controls.get_owned(principal.operator_id, command.command_id)
            if existing:
                if existing.payload_fingerprint != fingerprint(ControlTargetKind.DISCONNECT_MAILBOX,
                        command.connection_id, existing.target_generation, None):
                    raise IdempotencyConflictError("COMMAND_REUSE_CONFLICT")
                return existing
            generation = await self._connections.get_owned_generation(command.connection_id, principal.operator_id)
            payload = fingerprint(ControlTargetKind.DISCONNECT_MAILBOX, command.connection_id, generation, None)
            async with self._factory.request(principal) as uow:
                await self._authority.validate_request_write(uow, principal)
                existing = await uow.controls.get_owned(principal.operator_id, command.command_id)
                if existing:
                    if existing.payload_fingerprint != payload:
                        raise IdempotencyConflictError("COMMAND_REUSE_CONFLICT")
                    return existing
                receipt = ControlReceipt(command_id=command.command_id, operator_id=principal.operator_id,
                    target_kind=ControlTargetKind.DISCONNECT_MAILBOX, target_id=command.connection_id,
                    target_generation=generation, initiating_session_id=principal.session_id,
                    auth_version=principal.auth_version, admitted_at=self._clock.now(), payload_fingerprint=payload)
                await uow.controls.insert(receipt)
                await uow.commit()
            try:
                current = await self._connections.get_owned_generation(command.connection_id, principal.operator_id)
                if current != generation:
                    raise StaleVersionError("MAILBOX_GENERATION_CHANGED")
                if self._disconnect_flow is not None:
                    await self._disconnect_flow(principal, command.connection_id)
                elif self._runtime.is_busy:
                    raise RuntimeError("MAILBOX_DISCONNECT_FLOW_UNAVAILABLE")
                else:
                    await self._connections.disconnect(command.connection_id, owner=principal.operator_id)
            except Exception:
                async with self._factory.request(principal) as uow:
                    await uow.controls.mark_uncertain(principal.operator_id, command.command_id,
                        expected_version=receipt.version, reason="MAILBOX_DISCONNECT_UNKNOWN")
                    await uow.commit()
            else:
                async with self._factory.request(principal) as uow:
                    await uow.controls.complete(principal.operator_id, command.command_id,
                                                expected_version=receipt.version, result_code="COMPLETED")
                    await uow.commit()
            return await self.get_owned(principal, command.command_id)

    async def get_owned(self, principal, command_id):
        async with self._factory.owned(principal.operator_id) as uow:
            receipt = await uow.controls.get_owned(principal.operator_id, command_id)
        if receipt is None:
            raise EntityNotFoundError("NOT_FOUND")
        return receipt

    async def shutdown(self, deadline=None):
        self._closed = True
