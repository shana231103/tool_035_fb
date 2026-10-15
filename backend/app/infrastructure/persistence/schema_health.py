# File: backend/app/infrastructure/persistence/schema_health.py
from sqlalchemy import inspect, text
from app.domain.value_objects.enums import JobStatus, TaskStatus


async def check_schema(manager) -> None:
    def verify(connection):
        inspector = inspect(connection)
        required = {
            "owner_profiles": {"rights_owner_name", "sender_name", "rights_jurisdiction", "owner_role"},
            "report_tasks": {"attempt_id", "input_snapshot", "verification", "submitted_at", "receipt_text"},
        }
        for table, fields in required.items():
            names = {column["name"] for column in inspector.get_columns(table)}
            if not fields <= names:
                raise RuntimeError("Database needs migration: run python -m alembic -c backend/alembic.ini upgrade head.")
    await manager.validate_schema(verify)


async def check_browser_schema(manager) -> None:
    """Browser admission requires both migration evidence and structural constraints."""
    def verify(connection):
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        message = "Browser database needs migration: run python -m alembic -c backend/alembic.ini upgrade head."
        if not {"alembic_version", "browser_runtime_bindings", "browser_session_leases"} <= tables:
            raise RuntimeError(message)
        revisions = set(connection.execute(text("SELECT version_num FROM alembic_version")).scalars())
        if revisions != {"003_browser_ledger"}:
            raise RuntimeError(message)
        from app.infrastructure.persistence.browser_session_model import BrowserRuntimeBindingModel, BrowserSessionModel
        for model in (BrowserRuntimeBindingModel, BrowserSessionModel):
            fields = {c["name"]: c for c in inspector.get_columns(model.__tablename__)}
            for column in model.__table__.columns:
                if column.name not in fields or fields[column.name]["nullable"] != column.nullable:
                    raise RuntimeError(message)
            expected_pk = [column.name for column in model.__table__.primary_key.columns]
            if inspector.get_pk_constraint(model.__tablename__)["constrained_columns"] != expected_pk:
                raise RuntimeError(message)
        unique = {tuple(c["column_names"]) for c in inspector.get_unique_constraints("browser_session_leases")}
        if not {("installation_id", "task_id", "attempt_id"), ("provider_binding_id", "profile_id")} <= unique:
            raise RuntimeError(message)
        foreign = inspector.get_foreign_keys("browser_session_leases")
        if not any(f["constrained_columns"] == ["task_id"] and f["referred_table"] == "report_tasks"
                   and f["options"].get("ondelete", "").upper() == "RESTRICT" for f in foreign):
            raise RuntimeError(message)
        checks = {c["name"] for c in inspector.get_check_constraints("browser_session_leases")}
        binding_checks = {c["name"] for c in inspector.get_check_constraints("browser_runtime_bindings")}
        indexes = {c["name"]: tuple(c["column_names"]) for c in inspector.get_indexes("browser_session_leases")}
        if not {"ck_browser_charge", "ck_browser_counters"} <= checks or "ck_browser_singleton" not in binding_checks:
            raise RuntimeError(message)
        if (indexes.get("ix_browser_installation_charge") != ("installation_id", "charged", "updated_at")
                or indexes.get("ix_browser_task_charge") != ("installation_id", "task_id", "charged")):
            raise RuntimeError(message)
    await manager.validate_schema(verify)


async def recover_interrupted(factory) -> None:
    active = {TaskStatus.RUNNING, TaskStatus.WAITING_EMAIL_SLOT,
              TaskStatus.WAITING_EMAIL_CODE, TaskStatus.VERIFYING_EMAIL, TaskStatus.SUBMITTING}
    offset = 0
    while True:
        async with factory() as uow:
            jobs = await uow.jobs.list_jobs(limit=100, offset=offset)
            for job in jobs:
                changed = False
                for task in job.tasks:
                    if task.status in active:
                        task.mark_failed("Browser session lost on restart. No automatic resume.", False)
                        task.verification = {}
                        await uow.tasks.save(task)
                        changed = True
                if changed or job.status == JobStatus.RUNNING:
                    job.pause()
                    await uow.jobs.save(job)
        if len(jobs) < 100:
            break
        offset += 100
