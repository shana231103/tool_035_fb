# File: backend/app/infrastructure/persistence/operator_schema.py
"""Schema structural checks and allowed revision verification for operator accounts."""

from sqlalchemy import inspect, text

ALLOWED_REVISIONS = {
    "004_operator_accounts",
    "005_single_task_execution",
    "006_single_task_repair",
    "007_task_start_contract",
}


def verify_operator_schema_connection(connection) -> None:
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    message = (
        "Operator database needs migration: run python -m alembic -c "
        "backend/alembic.ini upgrade head."
    )
    if "alembic_version" not in tables:
        raise RuntimeError(message)

    revisions = set(
        connection.execute(text("SELECT version_num FROM alembic_version")).scalars()
    )
    from app.infrastructure.persistence.schema_manifest import POSTGRES_HEAD
    allowed = {POSTGRES_HEAD} if connection.dialect.name == "postgresql" else ALLOWED_REVISIONS
    if not revisions or not revisions <= allowed:
        raise RuntimeError(f"{message} Found revisions: {revisions}")

    required_tables = {
        "operator_accounts",
        "operator_sessions",
        "proxy_owner_refs",
        "operator_artifacts",
    }
    if not (required_tables <= tables):
        raise RuntimeError(f"{message} Missing tables: {required_tables - tables}")

    account_cols = {c["name"] for c in inspector.get_columns("operator_accounts")}
    if not {
        "id",
        "username_key",
        "status",
        "auth_version",
        "run_version",
    } <= account_cols:
        raise RuntimeError(f"{message} Incomplete operator_accounts schema.")

    session_cols = {c["name"] for c in inspector.get_columns("operator_sessions")}
    if not {
        "id",
        "secret_digest",
        "operator_id",
        "auth_version",
        "expires_at",
    } <= session_cols:
        raise RuntimeError(f"{message} Incomplete operator_sessions schema.")

    for scoped_table in ("owner_profiles", "proxies", "batch_jobs", "report_tasks"):
        if scoped_table in tables:
            cols = {c["name"] for c in inspector.get_columns(scoped_table)}
            if "operator_account_id" not in cols:
                raise RuntimeError(
                    f"{message} Table {scoped_table} missing operator_account_id"
                )


async def check_operator_schema(manager) -> None:
    await manager.validate_schema(verify_operator_schema_connection)
