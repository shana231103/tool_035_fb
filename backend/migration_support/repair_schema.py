# File: backend/migration_support/repair_schema.py
"""DDL generation and SQLite table repair routines for migration 006."""

import sqlalchemy as sa


def create_legacy_task_metadata_table(bind) -> None:
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "legacy_task_metadata" not in tables:
        bind.execute(
            sa.text(
                "CREATE TABLE legacy_task_metadata ("
                "id VARCHAR(36) PRIMARY KEY, "
                "source_revision VARCHAR(50) NOT NULL, "
                "raw_task_id VARCHAR(36) NULL, "
                "raw_batch_job_id VARCHAR(36) NULL, "
                "raw_profile_id VARCHAR(36) NULL, "
                "raw_proxy_id VARCHAR(36) NULL, "
                "raw_status VARCHAR(50) NULL, "
                "raw_targets TEXT NULL, "
                "raw_evidence TEXT NULL, "
                "pre_conversion_digest VARCHAR(64) NULL, "
                "disposition VARCHAR(50) NOT NULL DEFAULT 'READONLY', "
                "provenance TEXT NULL, "
                "created_at TIMESTAMP NOT NULL"
                ")"
            )
        )
        bind.execute(
            sa.text("CREATE INDEX ix_legacy_task_raw ON legacy_task_metadata(raw_task_id)")
        )


def repair_task_start_receipts(bind) -> None:
    inspector = sa.inspect(bind)
    if "task_start_receipts" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("task_start_receipts")}
    if "authority_contract_version" not in cols:
        bind.execute(
            sa.text(
                "ALTER TABLE task_start_receipts "
                "ADD COLUMN authority_contract_version INTEGER NOT NULL DEFAULT 1"
            )
        )


def repair_task_control_receipts(bind) -> None:
    inspector = sa.inspect(bind)
    if "task_control_receipts" not in inspector.get_table_names():
        return
    pk = inspector.get_pk_constraint("task_control_receipts")
    cols = pk.get("constrained_columns", [])
    if cols == ["operator_account_id", "command_id"]:
        return  # already composite PK

    bind.execute(
        sa.text(
            "CREATE TABLE task_control_receipts_new ("
            "operator_account_id VARCHAR(36) NOT NULL, "
            "command_id VARCHAR(36) NOT NULL, "
            "kind VARCHAR(50) NOT NULL, "
            "target_id TEXT NOT NULL, "
            "target_generation INTEGER NOT NULL, "
            "initiating_session_id VARCHAR(36) NOT NULL, "
            "auth_version INTEGER NOT NULL, "
            "admitted_at TIMESTAMP NOT NULL, "
            "status VARCHAR(30) NOT NULL DEFAULT 'ADMITTED', "
            "result_code VARCHAR(50) NOT NULL DEFAULT 'ADMITTED', "
            "completed_at TIMESTAMP NULL, "
            "version INTEGER NOT NULL DEFAULT 1, "
            "PRIMARY KEY (operator_account_id, command_id), "
            "FOREIGN KEY (operator_account_id) REFERENCES operator_accounts(id)"
            ")"
        )
    )
    bind.execute(
        sa.text(
            "INSERT INTO task_control_receipts_new ("
            "operator_account_id, command_id, kind, target_id, target_generation, "
            "initiating_session_id, auth_version, admitted_at, status, result_code, "
            "completed_at, version"
            ") "
            "SELECT operator_account_id, command_id, kind, target_id, target_generation, "
            "initiating_session_id, auth_version, admitted_at, status, result_code, "
            "completed_at, version FROM task_control_receipts"
        )
    )
    bind.execute(sa.text("DROP TABLE task_control_receipts"))
    bind.execute(
        sa.text("ALTER TABLE task_control_receipts_new RENAME TO task_control_receipts")
    )
    bind.execute(
        sa.text(
            "CREATE INDEX ix_task_control_receipts_owner "
            "ON task_control_receipts(operator_account_id)"
        )
    )
