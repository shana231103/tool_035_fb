# File: backend/app/application/operator_access.py
"""Execution run fences and mutation access guards."""

from typing import Any, Optional
from uuid import UUID

from app.domain.entities.operator_account import OperatorAccountStatus
from app.domain.exceptions.operator_errors import (
    AccountDisabledError,
    OperatorExecutionFenceError,
    OwnedResourceNotFoundError,
    SessionExpiredError,
    SessionRevokedError,
)
from app.domain.ports.operator_security import IClock
from app.domain.value_objects.operator_identity import ExecutionScope, OperatorPrincipal


class OperatorAccess:
    def __init__(self, clock: IClock):
        self._clock = clock

    def _check_owner(self, scope: Any, record: Any) -> None:
        if record is None:
            raise OwnedResourceNotFoundError("Record not found")
        rec_op_id = getattr(record, "operator_id", None)
        rec_op_acc_id = getattr(record, "operator_account_id", None)
        record_owner = rec_op_id or rec_op_acc_id
        op_id = getattr(scope, "operator_id", None)
        if record_owner is not None and op_id is not None and record_owner != op_id:
            raise OwnedResourceNotFoundError("Foreign resource access denied")

    async def require_request_write(
        self, uow: Any, principal: OperatorPrincipal
    ) -> None:
        now = self._clock.now()
        if now >= principal.absolute_expires_at:
            raise SessionExpiredError("Session absolute timeout expired")
        if now >= principal.idle_expires_at:
            raise SessionExpiredError("Session idle timeout expired")

        if hasattr(uow, "accounts") and uow.accounts:
            account = await uow.accounts.get(principal.operator_id)
            if not account or account.status != OperatorAccountStatus.ACTIVE:
                raise AccountDisabledError("Operator account is not active")
            if account.auth_version != principal.auth_version:
                raise SessionRevokedError("Session revoked due to auth version bump")

    async def require_run(self, uow: Any, grant: Any) -> None:
        scope = getattr(grant, "scope", grant)
        if hasattr(uow, "accounts") and uow.accounts:
            account = await uow.accounts.get(scope.operator_id)
            if not account or account.status != OperatorAccountStatus.ACTIVE:
                raise AccountDisabledError("Operator account is disabled or missing")
            if account.run_version != scope.run_version:
                raise OperatorExecutionFenceError("Stale run version detected")
        task_id = getattr(scope, "task_id", None)
        if task_id and hasattr(uow, "tasks"):
            task = await uow.tasks.get_by_id(task_id)
            self._check_owner(scope, task)

    async def admit_submitting(
        self,
        uow: Any,
        grant: Any,
        *,
        expected_task_version: Optional[int] = None,
        input_digest: Optional[str] = None,
    ) -> None:
        await self.require_run(uow, grant)
        scope = getattr(grant, "scope", grant)
        task_id = getattr(scope, "task_id", None)
        if task_id and hasattr(uow, "tasks"):
            task = await uow.tasks.get_by_id(task_id)
            if not task:
                raise OwnedResourceNotFoundError("Task not found")
            self._check_owner(scope, task)
            if expected_task_version is not None and task.version != expected_task_version:
                raise OperatorExecutionFenceError("Stale task version on submission admission")
