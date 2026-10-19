# File: backend/app/infrastructure/persistence/schema_manifest.py
"""Full structural schema manifest and runtime validator for Phase 004b (head 006)."""

from typing import Any, Dict, Set
from sqlalchemy import inspect, text

CURRENT_HEAD: str = "007_task_start_contract"
ALLOWED_REVISIONS: Set[str] = {"007_task_start_contract"}
POSTGRES_HEAD = "002_task_start_contract"

REQUIRED_TABLE_COLUMNS: Dict[str, Set[str]] = {
    "operator_accounts": {"id", "username_key", "username_display", "status", "auth_version", "run_version"},
    "operator_sessions": {"id", "operator_id", "secret_digest", "auth_version", "expires_at", "idle_expires_at"},
    "owner_profiles": {"id", "operator_account_id", "rights_owner_name", "sender_name", "rights_jurisdiction", "owner_role"},
    "proxies": {"id", "operator_account_id", "host", "port", "protocol", "country"},
    "proxy_owner_refs": {"proxy_id", "operator_account_id"},
    "report_tasks": {"id", "operator_account_id", "target_urls_json", "version", "name", "status"},
    "browser_runtime_bindings": {"singleton_id", "installation_id", "provider_binding_id"},
    "browser_session_leases": {"operation_id", "installation_id", "profile_id", "task_id", "attempt_id", "charged"},
    "operator_artifacts": {"id", "operator_account_id", "kind", "storage_key"},
    "task_artifact_links": {"artifact_id", "task_id", "operator_account_id", "kind"},
    "task_start_receipts": {"operator_account_id", "command_id", "task_id", "attempt_id", "authority_contract_version", "outcome_phase"},
    "task_control_receipts": {"operator_account_id", "command_id", "kind", "target_id", "status", "payload_fingerprint", "expected_task_version", "attempt_id", "authority_contract_version", "version"},
    "task_execution_slot": {"singleton_id", "generation", "phase"},
    "legacy_task_metadata": {"id", "source_revision", "raw_task_id", "disposition"},
}


def verify_manifest(connection: Any) -> Dict[str, Any]:
    """Validate that the active connection conforms strictly to head 006 manifest."""
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    head = POSTGRES_HEAD if connection.dialect.name == "postgresql" else CURRENT_HEAD
    config = "backend/alembic_postgres.ini" if connection.dialect.name == "postgresql" else "backend/alembic.ini"
    msg = f"Database needs migration to head {head}: run python -m alembic -c {config} upgrade head."

    if "alembic_version" not in tables:
        raise RuntimeError(f"{msg} Missing alembic_version table.")

    revisions = set(connection.execute(text("SELECT version_num FROM alembic_version")).scalars())
    if revisions != {head}:
        raise RuntimeError(f"{msg} Expected head '{head}', found: {revisions}")

    missing_tables = set(REQUIRED_TABLE_COLUMNS.keys()) - tables
    if missing_tables:
        raise RuntimeError(f"{msg} Missing required tables: {missing_tables}")

    for tbl, cols in REQUIRED_TABLE_COLUMNS.items():
        existing_cols = {c["name"] for c in inspector.get_columns(tbl)}
        missing_cols = cols - existing_cols
        if missing_cols:
            raise RuntimeError(f"{msg} Table '{tbl}' missing columns: {missing_cols}")

    expected_checks = {"task_start_receipts": {"ck_start_receipt_contract"},
        "task_control_receipts": {"ck_control_receipt_contract", "ck_control_receipt_version"},
        "operator_artifacts": {"ck_artifact_resource"},
        "report_tasks": {"ck_report_task_version_positive"},
        "task_execution_slot": {"ck_slot_generation_nonnegative"}}
    for table, names in expected_checks.items():
        checks = {item["name"] for item in inspector.get_check_constraints(table)}
        if not names <= checks:
            raise RuntimeError(f"{msg} Missing contract constraints for {table}.")
    artifacts = {c["name"]: c for c in inspector.get_columns("operator_artifacts")}
    if not artifacts["job_id"]["nullable"]:
        raise RuntimeError(f"{msg} Task artifacts require nullable legacy job_id.")
    slot = connection.execute(
        text("SELECT singleton_id, generation, phase FROM task_execution_slot WHERE singleton_id = 1")
    ).fetchone()
    if not slot:
        raise RuntimeError(f"{msg} task_execution_slot row singleton_id=1 is missing.")

    active_dummy = connection.execute(
        text("SELECT COUNT(*) FROM operator_accounts WHERE username_key = 'system_default' AND status = 'ACTIVE'")
    ).scalar() or 0
    if active_dummy > 0:
        raise RuntimeError("Security violation: synthetic default operator account cannot remain ACTIVE.")

    if connection.dialect.name == "sqlite":
        fk_errors = connection.execute(text("PRAGMA foreign_key_check")).fetchall()
        if fk_errors:
            raise RuntimeError(f"Foreign key verification failed: {fk_errors}")

    return {"verified": True, "head": head, "slot_phase": slot[2], "slot_generation": slot[1]}
