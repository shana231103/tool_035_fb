# File: backend/migration_support/single_task_verify.py
"""Verification helpers for single task execution schema and data integrity."""

from typing import Any, Dict
import sqlalchemy as sa


def verify_single_task_schema(bind) -> Dict[str, Any]:
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    required_tables = {
        "report_tasks",
        "task_execution_slot",
        "task_start_receipts",
        "task_control_receipts",
        "task_artifact_links",
    }
    missing_tables = required_tables - tables
    if missing_tables:
        raise RuntimeError(f"Missing required standalone task tables: {missing_tables}")

    task_cols = {c["name"] for c in inspector.get_columns("report_tasks")}
    required_cols = {
        "target_urls_json",
        "version",
        "legacy_batch_job_id",
        "legacy_read_only",
        "name",
        "status",
    }
    missing_cols = required_cols - task_cols
    if missing_cols:
        raise RuntimeError(f"Missing required report_tasks columns: {missing_cols}")

    slot_row = bind.execute(
        sa.text("SELECT singleton_id, generation, phase FROM task_execution_slot WHERE singleton_id = 1")
    ).fetchone()
    if not slot_row:
        raise RuntimeError("task_execution_slot singleton row (singleton_id=1) is missing.")

    dialect = bind.dialect.name
    if dialect == "sqlite":
        fk_errors = bind.execute(sa.text("PRAGMA foreign_key_check")).fetchall()
        if fk_errors:
            raise RuntimeError(f"Foreign key verification failed after task migration: {fk_errors}")

    task_count = bind.execute(sa.text("SELECT COUNT(*) FROM report_tasks")).scalar() or 0
    link_count = bind.execute(sa.text("SELECT COUNT(*) FROM task_artifact_links")).scalar() or 0

    return {
        "verified": True,
        "slot_phase": slot_row[2],
        "slot_generation": slot_row[1],
        "task_count": task_count,
        "artifact_links_count": link_count,
    }
