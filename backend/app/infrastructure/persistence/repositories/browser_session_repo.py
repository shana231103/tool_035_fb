# File: backend/app/infrastructure/persistence/repositories/browser_session_repo.py
from uuid import UUID
from sqlalchemy import Integer, func, select, true, update
from sqlalchemy.exc import IntegrityError
from app.domain.exceptions.browser_errors import BrowserLedgerConflict, BrowserOwnershipError, BrowserUnavailable
from app.domain.ports.browser_ledger import IBrowserSessionLedger
from app.domain.value_objects.browser_session import BrowserPhase, BrowserSessionMutation, BrowserSessionRecord, CleanupState, CompletionEvidence
from app.domain.value_objects.browser_status import BrowserBootstrapSnapshot, BrowserLedgerCounts, RuntimeBinding
from app.domain.value_objects.browser_transitions import apply_mutation
from app.infrastructure.persistence.browser_session_model import BrowserRuntimeBindingModel as Binding, BrowserSessionModel as Lease
from app.infrastructure.persistence.repositories.browser_ledger_mapping import binding_value, record_columns, record_value


class BrowserSessionRepository(IBrowserSessionLedger):
    def __init__(self, session):
        self._session = session

    async def read_bootstrap_snapshot(self, limit: int = 1000) -> BrowserBootstrapSnapshot:
        if not 1 <= limit <= 10000:
            raise ValueError("Invalid browser bootstrap limit.")
        totals = select(func.count().label("rows"), func.coalesce(func.sum(Lease.charged.cast(Integer)), 0).label("charged"),
                        func.count().filter(Lease.phase != BrowserPhase.CLOSED.value).label("unclosed")).select_from(Lease).subquery()
        statement = select(Binding, Lease, totals.c.rows, totals.c.charged, totals.c.unclosed).select_from(totals)
        statement = statement.outerjoin(Binding, true()).outerjoin(Lease, Lease.phase != BrowserPhase.CLOSED.value)
        result = (await self._session.execute(statement.order_by(Lease.operation_id).limit(limit + 1))).all()
        first = result[0]
        records = tuple(record_value(row[1]) for row in result[:limit] if row[1] is not None)
        return BrowserBootstrapSnapshot(binding_value(first[0]), records, first[2], first[3], first[4] <= limit)

    async def initialize_binding_if_empty(self, binding: RuntimeBinding) -> RuntimeBinding:
        await self._session.execute(update(Binding).where(Binding.singleton_id == 1)
                                    .values(schema_version=Binding.schema_version))
        current = (await self._session.execute(select(Binding).where(Binding.singleton_id == 1))).scalar_one_or_none()
        if current is not None:
            if binding_value(current) != binding:
                raise BrowserOwnershipError()
            foreign = select(func.count()).select_from(Lease).where(
                (Lease.installation_id != str(binding.installation_id)) | (Lease.provider_binding_id != str(binding.provider_binding_id)))
            if (await self._session.execute(foreign)).scalar_one():
                raise BrowserOwnershipError()
            return binding
        if (await self._session.execute(select(func.count()).select_from(Lease))).scalar_one():
            raise BrowserOwnershipError()
        self._session.add(Binding(singleton_id=1, installation_id=str(binding.installation_id),
                                  provider_binding_id=str(binding.provider_binding_id),
                                  host_binding_digest=binding.host_binding_digest, schema_version=binding.schema_version))
        try:
            await self._session.flush()
        except IntegrityError:
            raise BrowserLedgerConflict() from None
        return binding

    async def _lock_binding(self) -> RuntimeBinding:
        # Write lock serializes reservation/counting on SQLite; row lock on PostgreSQL.
        result = await self._session.execute(update(Binding).where(Binding.singleton_id == 1)
                                             .values(schema_version=Binding.schema_version))
        if result.rowcount != 1:
            raise BrowserOwnershipError()
        model = (await self._session.execute(select(Binding).where(Binding.singleton_id == 1))).scalar_one()
        return binding_value(model)

    async def reserve(self, record: BrowserSessionRecord, limit: int) -> None:
        if (limit < 1 or record.phase != BrowserPhase.RESERVED or record.version != 0 or not record.charged
                or record.profile_id is not None or record.cleanup_state != CleanupState.NOT_STARTED
                or record.completion_evidence != CompletionEvidence.UNKNOWN or record.retries != 0
                or record.next_retry_at is not None or record.audit_reference is not None):
            raise BrowserLedgerConflict(record.operation_id)
        binding = await self._lock_binding()
        if binding.installation_id != record.installation_id or binding.provider_binding_id != record.provider_binding_id:
            raise BrowserOwnershipError(operation_id=record.operation_id)
        foreign = select(func.count()).select_from(Lease).where(Lease.phase != BrowserPhase.CLOSED.value).where(
            (Lease.installation_id != str(record.installation_id)) | (Lease.provider_binding_id != str(record.provider_binding_id)))
        if (await self._session.execute(foreign)).scalar_one():
            raise BrowserOwnershipError(operation_id=record.operation_id)
        if await self.get_unclosed_for_task(record.task_id):
            raise BrowserLedgerConflict(record.operation_id)
        charged = (await self._session.execute(select(func.count()).select_from(Lease).where(Lease.charged.is_(True)))).scalar_one()
        if charged >= limit:
            raise BrowserUnavailable("BROWSER_CAPACITY_WAIT", operation_id=record.operation_id)
        self._session.add(Lease(**record_columns(record)))
        try:
            await self._session.flush()
        except IntegrityError:
            raise BrowserLedgerConflict(record.operation_id) from None

    async def get(self, operation_id: UUID) -> BrowserSessionRecord | None:
        model = (await self._session.execute(select(Lease).where(Lease.operation_id == str(operation_id))
                                            .execution_options(populate_existing=True))).scalar_one_or_none()
        return record_value(model) if model is not None else None

    async def _unclosed(self, condition) -> tuple[BrowserSessionRecord, ...]:
        result = await self._session.execute(select(Lease).where(Lease.phase != BrowserPhase.CLOSED.value, condition)
                                             .order_by(Lease.created_at, Lease.operation_id))
        return tuple(record_value(model) for model in result.scalars())

    async def get_unclosed_for_task(self, task_id: UUID) -> tuple[BrowserSessionRecord, ...]:
        return await self._unclosed(Lease.task_id == str(task_id))

    async def list_unclosed(self, installation_id: UUID) -> tuple[BrowserSessionRecord, ...]:
        return await self._unclosed(Lease.installation_id == str(installation_id))

    async def mutate(self, operation_id: UUID, expected_version: int,
                     mutation: BrowserSessionMutation) -> BrowserSessionRecord:
        binding = await self._lock_binding()
        record = await self.get(operation_id)
        if record is None or record.version != expected_version:
            raise BrowserLedgerConflict(operation_id)
        if record.installation_id != binding.installation_id or record.provider_binding_id != binding.provider_binding_id:
            raise BrowserOwnershipError(operation_id=operation_id)
        changed = apply_mutation(record, mutation)
        values = record_columns(changed)
        for name in ("operation_id", "installation_id", "provider_binding_id", "task_id", "attempt_id", "marker_nonce", "created_at"):
            values.pop(name)
        try:
            result = await self._session.execute(update(Lease).where(Lease.operation_id == str(operation_id),
                                                 Lease.version == expected_version).values(**values))
            if result.rowcount != 1:
                raise BrowserLedgerConflict(operation_id)
            await self._session.flush()
        except IntegrityError:
            raise BrowserLedgerConflict(operation_id) from None
        return changed

    async def summarize(self, installation_id: UUID) -> BrowserLedgerCounts:
        stmt = select(func.count().filter(Lease.charged.is_(True)),
                      func.count().filter(Lease.cleanup_state.in_([CleanupState.PENDING.value, CleanupState.RETRY_EXHAUSTED.value, CleanupState.UNRESOLVED.value])),
                      func.count().filter(Lease.phase.in_([BrowserPhase.UNKNOWN_CREATE.value, BrowserPhase.DELETE_UNKNOWN.value, BrowserPhase.NEEDS_OPERATOR.value])),
                      func.count().filter(Lease.phase != BrowserPhase.CLOSED.value)).where(Lease.installation_id == str(installation_id))
        return BrowserLedgerCounts(*(await self._session.execute(stmt)).one())
