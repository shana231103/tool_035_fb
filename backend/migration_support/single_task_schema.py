# File: backend/migration_support/single_task_schema.py
"""Schema creation and SQLite table rebuild helpers for standalone tasks."""

import sqlalchemy as sa


def create_standalone_task_tables(bind) -> None:
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "task_execution_slot" not in tables:
        bind.execute(
            sa.text(
                "CREATE TABLE task_execution_slot ("
                "singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1), "
                "generation INTEGER NOT NULL DEFAULT 0, "
                "phase VARCHAR(30) NOT NULL DEFAULT 'FREE', "
                "task_id VARCHAR(36) NULL, "
                "operator_account_id VARCHAR(36) NULL, "
                "attempt_id VARCHAR(36) NULL, "
                "run_version INTEGER NULL, "
                "command_id VARCHAR(36) NULL, "
                "runtime_epoch VARCHAR(36) NULL, "
                "admitted_at TIMESTAMP NULL, "
                "recovery_id VARCHAR(36) NULL, "
                "recovery_reason TEXT NULL, "
                "recovery_started_at TIMESTAMP NULL, "
                "FOREIGN KEY (task_id, operator_account_id) "
                "REFERENCES report_tasks(id, operator_account_id), "
                "CONSTRAINT ck_slot_phase_invariants CHECK ("
                "(phase = 'FREE' AND task_id IS NULL AND operator_account_id IS NULL AND "
                "attempt_id IS NULL AND run_version IS NULL AND command_id IS NULL AND "
                "runtime_epoch IS NULL AND admitted_at IS NULL AND recovery_id IS NULL AND "
                "recovery_reason IS NULL AND recovery_started_at IS NULL) OR "
                "(phase IN ('ADMITTED', 'RUNNING', 'DRAINING') AND task_id IS NOT NULL AND "
                "operator_account_id IS NOT NULL AND attempt_id IS NOT NULL AND "
                "run_version IS NOT NULL AND command_id IS NOT NULL AND runtime_epoch IS NOT NULL "
                "AND admitted_at IS NOT NULL AND recovery_id IS NULL AND recovery_reason IS NULL "
                "AND recovery_started_at IS NULL) OR "
                "(phase = 'RECOVERY_REQUIRED' AND recovery_id IS NOT NULL AND recovery_reason IS NOT NULL "
                "AND recovery_started_at IS NOT NULL AND ("
                "(task_id IS NOT NULL AND operator_account_id IS NOT NULL AND attempt_id IS NOT NULL "
                "AND run_version IS NOT NULL AND command_id IS NOT NULL AND runtime_epoch IS NOT NULL "
                "AND admitted_at IS NOT NULL) OR "
                "(task_id IS NULL AND operator_account_id IS NULL AND attempt_id IS NULL AND "
                "run_version IS NULL AND command_id IS NULL AND runtime_epoch IS NULL AND admitted_at IS NULL)"
                "))))"
            )
        )

    if "task_start_receipts" not in tables:
        bind.execute(
            sa.text(
                "CREATE TABLE task_start_receipts ("
                "operator_account_id VARCHAR(36) NOT NULL, "
                "command_id VARCHAR(36) NOT NULL, "
                "task_id VARCHAR(36) NOT NULL, "
                "attempt_id VARCHAR(36) NOT NULL, "
                "slot_generation INTEGER NOT NULL, "
                "run_version INTEGER NOT NULL, "
                "runtime_epoch VARCHAR(36) NOT NULL, "
                "admitted_task_version INTEGER NOT NULL, "
                "admitted_at TIMESTAMP NOT NULL, "
                "payload_fingerprint TEXT NOT NULL, "
                "outcome_phase VARCHAR(30) NOT NULL DEFAULT 'ADMITTED', "
                "PRIMARY KEY (operator_account_id, command_id), "
                "FOREIGN KEY (operator_account_id) REFERENCES operator_accounts(id), "
                "FOREIGN KEY (task_id, operator_account_id) REFERENCES report_tasks(id, operator_account_id)"
                ")"
            )
        )
        bind.execute(
            sa.text(
                "CREATE INDEX ix_task_start_receipts_task "
                "ON task_start_receipts(task_id, operator_account_id, admitted_at)"
            )
        )

    if "task_control_receipts" not in tables:
        bind.execute(
            sa.text(
                "CREATE TABLE task_control_receipts ("
                "command_id VARCHAR(36) PRIMARY KEY, "
                "operator_account_id VARCHAR(36) NOT NULL, "
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
                "FOREIGN KEY (operator_account_id) REFERENCES operator_accounts(id)"
                ")"
            )
        )
        bind.execute(
            sa.text(
                "CREATE INDEX ix_task_control_receipts_owner "
                "ON task_control_receipts(operator_account_id)"
            )
        )

    if "task_artifact_links" not in tables:
        bind.execute(
            sa.text(
                "CREATE TABLE task_artifact_links ("
                "artifact_id VARCHAR(36) NOT NULL, "
                "task_id VARCHAR(36) NOT NULL, "
                "operator_account_id VARCHAR(36) NOT NULL, "
                "kind VARCHAR(20) NOT NULL, "
                "created_at TIMESTAMP NOT NULL, "
                "PRIMARY KEY (artifact_id, task_id), "
                "FOREIGN KEY (operator_account_id) REFERENCES operator_accounts(id), "
                "FOREIGN KEY (task_id, operator_account_id) REFERENCES report_tasks(id, operator_account_id)"
                ")"
            )
        )
        bind.execute(
            sa.text(
                "CREATE INDEX ix_task_artifact_links_lookup "
                "ON task_artifact_links(task_id, operator_account_id)"
            )
        )


def rebuild_report_tasks_table(bind) -> None:
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "report_tasks" not in tables:
        return

    cols = {c["name"] for c in inspector.get_columns("report_tasks")}
    if "target_urls_json" in cols and "legacy_batch_job_id" in cols:
        return  # already rebuilt

    bind.execute(
        sa.text(
            "CREATE TABLE report_tasks_new ("
            "id VARCHAR(36) PRIMARY KEY, "
            "operator_account_id VARCHAR(36) NOT NULL, "
            "name VARCHAR(255) NOT NULL DEFAULT 'Report Task', "
            "owner_profile_id VARCHAR(36) NULL, "
            "preferred_country VARCHAR(10) NULL, "
            "target_urls_json TEXT NOT NULL DEFAULT '[]', "
            "version INTEGER NOT NULL DEFAULT 1, "
            "run_version INTEGER NULL, "
            "last_start_command_id VARCHAR(36) NULL, "
            "legacy_read_only BOOLEAN NOT NULL DEFAULT 0, "
            "display_summary TEXT NULL, "
            "legacy_batch_job_id VARCHAR(36) NULL, "
            "batch_job_id VARCHAR(36) NULL, "
            "target_url TEXT NULL, "
            "target_platform VARCHAR(50) NULL DEFAULT 'FACEBOOK', "
            "target_content_type VARCHAR(50) NULL DEFAULT 'post', "
            "original_url TEXT NOT NULL, "
            "explanation TEXT NOT NULL, "
            "status VARCHAR(50) NOT NULL DEFAULT 'DRAFT', "
            "retry_count INTEGER NOT NULL DEFAULT 0, "
            "max_retries INTEGER NOT NULL DEFAULT 3, "
            "proxy_id VARCHAR(36) NULL, "
            "meta_case_number VARCHAR(100) NULL, "
            "screenshot_path VARCHAR(500) NULL, "
            "error_message TEXT NULL, "
            "infringing_account VARCHAR(255) NULL, "
            "created_at TIMESTAMP NOT NULL, "
            "updated_at TIMESTAMP NOT NULL, "
            "completed_at TIMESTAMP NULL, "
            "attempt_id VARCHAR(36) NULL, "
            "input_snapshot JSON NULL, "
            "verification JSON NULL, "
            "submitted_at TIMESTAMP NULL, "
            "receipt_text TEXT NULL, "
            "CONSTRAINT uq_report_tasks_owner UNIQUE (id, operator_account_id), "
            "FOREIGN KEY (operator_account_id) REFERENCES operator_accounts(id), "
            "FOREIGN KEY (owner_profile_id, operator_account_id) "
            "REFERENCES owner_profiles(id, operator_account_id), "
            "FOREIGN KEY (legacy_batch_job_id) REFERENCES batch_jobs(id)"
            ")"
        )
    )

    bind.execute(
        sa.text(
            "INSERT INTO report_tasks_new ("
            "id, operator_account_id, name, owner_profile_id, preferred_country, "
            "target_urls_json, version, run_version, last_start_command_id, "
            "legacy_read_only, display_summary, legacy_batch_job_id, batch_job_id, "
            "target_url, target_platform, target_content_type, original_url, explanation, "
            "status, retry_count, max_retries, proxy_id, meta_case_number, screenshot_path, "
            "error_message, infringing_account, created_at, updated_at, completed_at, "
            "attempt_id, input_snapshot, verification, submitted_at, receipt_text"
            ") "
            "SELECT id, operator_account_id, "
            "COALESCE('Task ' || substr(id, 1, 8), 'Report Task'), "
            "NULL, NULL, "
            "CASE WHEN target_url IS NOT NULL AND target_url != '' "
            "THEN '[\"' || target_url || '\"]' ELSE '[]' END, "
            "1, NULL, NULL, 0, NULL, batch_job_id, batch_job_id, "
            "target_url, target_platform, target_content_type, original_url, explanation, "
            "CASE WHEN status IN ('PENDING', 'QUEUED', 'WAITING_EMAIL_SLOT') THEN 'DRAFT' "
            "ELSE status END, "
            "COALESCE(retry_count, 0), COALESCE(max_retries, 3), proxy_id, "
            "meta_case_number, screenshot_path, error_message, infringing_account, "
            "created_at, created_at, completed_at, attempt_id, input_snapshot, "
            "verification, submitted_at, receipt_text "
            "FROM report_tasks"
        )
    )

    bind.execute(sa.text("DROP TABLE report_tasks"))
    bind.execute(sa.text("ALTER TABLE report_tasks_new RENAME TO report_tasks"))

    bind.execute(
        sa.text(
            "CREATE INDEX ix_report_tasks_operator_created "
            "ON report_tasks(operator_account_id, created_at, id)"
        )
    )
    bind.execute(
        sa.text(
            "CREATE INDEX ix_report_tasks_operator_status "
            "ON report_tasks(operator_account_id, status, updated_at)"
        )
    )
