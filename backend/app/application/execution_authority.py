# File: backend/app/application/execution_authority.py
"""Transaction-local authority for already admitted report attempts."""
from app.domain.exceptions.task_errors import StaleVersionError
from app.domain.value_objects.operator_identity import OperatorAccountStatus
from app.domain.value_objects.task_execution import SlotPhase


class ExecutionAuthority:
    def __init__(self, clock):
        self._clock = clock

    def validate_proxy(self, endpoint):
        if endpoint is not None and self._clock.now() >= endpoint.valid_until:
            raise ValueError("PROXY_PREPARATION_EXPIRED")

    async def match_grant(self, uow, grant):
        slot = await uow.slot.read()
        task = await uow.tasks.get_by_id(grant.scope.task_id)
        if (slot.grant != grant or slot.generation != grant.slot_generation
                or slot.phase not in (SlotPhase.ADMITTED, SlotPhase.RUNNING, SlotPhase.DRAINING)
                or task is None or task.operator_id != grant.scope.operator_id
                or task.attempt_id != grant.attempt_id or task.run_version != grant.run_version
                or task.last_start_command_id != grant.command_id):
            raise StaleVersionError("EXECUTION_GRANT_MISMATCH")
        return task

    async def require_run(self, uow, grant):
        task = await self.match_grant(uow, grant)
        account = await uow.accounts.get(grant.scope.operator_id)
        if account is None or account.status != OperatorAccountStatus.ACTIVE or account.run_version != grant.run_version:
            raise StaleVersionError("EXECUTION_AUTHORITY_REVOKED")
        return task

    async def admit_submitting(self, uow, grant, *, expected_task_version, input_digest):
        task = await self.require_run(uow, grant)
        if task.version != expected_task_version or task.input_snapshot.get("input_digest") != input_digest:
            raise StaleVersionError("TASK_VERSION_CONFLICT")
        prior = task.version
        task.admit_submitting()
        await uow.tasks.save(task, expected_version=prior, expected_attempt_id=grant.attempt_id)
        return task
