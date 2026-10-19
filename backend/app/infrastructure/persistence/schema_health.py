# File: backend/app/infrastructure/persistence/schema_health.py
"""Schema health checks and migration revision validation for Phase 004c."""

from sqlalchemy import inspect, text
from app.infrastructure.persistence.schema_manifest import (
    CURRENT_HEAD,
    ALLOWED_REVISIONS,
    verify_manifest,
    POSTGRES_HEAD,
)


ALLOWED_BROWSER_REVISIONS = {
    "003_browser_ledger",
    "004_operator_accounts",
    "005_single_task_execution",
    "006_single_task_repair",
    "007_task_start_contract",
}


async def check_schema(manager) -> None:
    """Validate that the database schema satisfies the configured exact-head manifest."""
    await manager.validate_schema(verify_manifest)


async def check_browser_schema(manager) -> None:
    """Browser admission requires migration evidence and structural constraints."""
    def verify(connection):
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        message = "Browser database needs migration: run python -m alembic -c backend/alembic.ini upgrade head."
        if not {"alembic_version", "browser_runtime_bindings", "browser_session_leases"} <= tables:
            raise RuntimeError(message)
        revisions = set(connection.execute(text("SELECT version_num FROM alembic_version")).scalars())
        allowed = {POSTGRES_HEAD} if connection.dialect.name == "postgresql" else ALLOWED_BROWSER_REVISIONS
        if not (revisions & allowed):
            raise RuntimeError(f"{message} Found revisions: {revisions}")
        from app.infrastructure.persistence.browser_session_model import (
            BrowserRuntimeBindingModel,
            BrowserSessionModel,
        )
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


async def recover_interrupted(factory=None) -> None:
    """Reject the obsolete recovery entry point lacking a runtime ownership census."""
    raise RuntimeError("TaskRecoveryService with installation authority is required for recovery.")
