# File: backend/app/application/execution_budget.py
import asyncio
from uuid import uuid4

from app.application.execution_context import (
    BudgetSnapshot, DispatchPermit, DrainConfirmed, DrainPending,
    RecoveredResourceHold, UnusedPermitConfirmed,
)
from app.domain.value_objects.mailbox_verification import normalize_email


class ExecutionBudget:
    """Single-loop atomic capacity and email ownership, including unresolved drains."""

    def __init__(self, limit: int):
        if not 1 <= limit <= 3:
            raise ValueError("Execution capacity must be between one and three.")
        self.limit = limit
        self._incarnation = uuid4()
        self._permits = {}
        self._held = set()
        self._unknown = set()
        self._seeded = set()
        self._attempts = {}
        self._revision = 0
        self._event = asyncio.Event()
        self._closed = False

    def _signal(self):
        previous, self._event = self._event, asyncio.Event()
        self._revision += 1
        previous.set()

    def limit_to(self, limit: int) -> None:
        self.limit = min(self.limit, max(0, limit))
        self._signal()

    def email_busy(self, email: str) -> bool:
        canonical = normalize_email(email)
        return any(item.email == canonical for item in self._permits.values())

    def try_acquire(self, task_id, email) -> DispatchPermit | None:
        canonical = normalize_email(email)
        if (self._closed or self._unknown or len(self._permits) >= self.limit
                or self.email_busy(canonical)):
            return None
        permit = DispatchPermit(uuid4(), self._incarnation, task_id, canonical)
        self._permits[permit.id] = permit
        self._signal()
        return permit

    def _verify(self, permit):
        if (permit.budget_incarnation != self._incarnation
                or self._permits.get(permit.id) != permit):
            raise ValueError("Dispatch permit is no longer owned.")

    def hold_for_drain(self, permit, evidence: DrainPending) -> None:
        self._verify(permit)
        if evidence.permit_id != permit.id or evidence.task_id != permit.task_id:
            raise ValueError("Drain identity mismatch.")
        self._held.add(permit.id)
        self._signal()

    def bind_attempt(self, permit, attempt_id):
        self._verify(permit)
        previous = self._attempts.get(permit.id)
        if previous is not None and previous != attempt_id:
            raise ValueError("Dispatch attempt identity changed.")
        self._attempts[permit.id] = attempt_id

    def attempt_for(self, permit):
        self._verify(permit)
        return self._attempts.get(permit.id)

    def release(self, permit, evidence: DrainConfirmed | UnusedPermitConfirmed) -> None:
        self._verify(permit)
        valid = evidence.permit_id == permit.id and evidence.task_id == permit.task_id
        if isinstance(evidence, UnusedPermitConfirmed):
            valid = (valid and evidence.budget_incarnation == self._incarnation
                     and evidence.no_registered_work and evidence.provider_not_entered
                     and evidence.claim_state in ("NOT_APPLIED", "RESTORED_UNSTARTED"))
        else:
            valid = (valid and evidence.collector_joined and evidence.resource_clear
                     and evidence.attempt_id == self._attempts.get(permit.id))
        if not valid:
            raise ValueError("Resource drain has not been confirmed.")
        del self._permits[permit.id]
        self._held.discard(permit.id)
        self._unknown.discard(permit.id)
        self._attempts.pop(permit.id, None)
        self._signal()

    def seed_holds(self, holds: tuple[RecoveredResourceHold, ...]) -> tuple[DispatchPermit, ...]:
        seeded = []
        for hold in holds:
            if hold.operation_id in self._seeded:
                continue
            self._seeded.add(hold.operation_id)
            email = normalize_email(hold.email) if hold.email else None
            permit = DispatchPermit(uuid4(), self._incarnation, hold.task_id, email)
            self._permits[permit.id] = permit
            self._held.add(permit.id)
            self._attempts[permit.id] = hold.attempt_id
            if email is None:
                self._unknown.add(permit.id)
            seeded.append(permit)
        self._signal()
        return tuple(seeded)

    def snapshot(self) -> BudgetSnapshot:
        return BudgetSnapshot(self.limit, len(self._permits) - len(self._held),
                              len(self._held), self._revision, self._closed, bool(self._unknown))

    async def wait_changed(self, after_revision: int) -> int:
        while self._revision <= after_revision and not self._closed:
            current = self._event
            await current.wait()
        return self._revision

    def close(self) -> None:
        self._closed = True
        self._signal()
