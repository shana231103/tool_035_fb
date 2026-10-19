# File: backend/migration_support/single_task_backfill.py
"""Backfill and execution slot initialization helpers for single task execution migration."""

from datetime import datetime, timezone
from uuid import uuid4
import sqlalchemy as sa


def _now() -> datetime:
    return datetime.now(timezone.utc)


def backfill_task_artifact_links(bind) -> None:
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "operator_artifacts" not in tables or "task_artifact_links" not in tables:
        return

    bind.execute(
        sa.text(
            "INSERT OR IGNORE INTO task_artifact_links ("
            "artifact_id, task_id, operator_account_id, kind, created_at"
            ") "
            "SELECT a.id, a.task_id, a.operator_account_id, a.kind, a.created_at "
            "FROM operator_artifacts a "
            "JOIN report_tasks t ON t.id = a.task_id AND t.operator_account_id = a.operator_account_id "
            "WHERE a.task_id IS NOT NULL"
        )
    )


def initialize_execution_slot(bind) -> None:
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "task_execution_slot" not in tables:
        return

    slot_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM task_execution_slot WHERE singleton_id = 1")
    ).scalar()

    if slot_count and slot_count > 0:
        return  # Slot singleton already initialized

    has_inflight = False
    if "report_tasks" in tables:
        inflight_count = bind.execute(
            sa.text(
                "SELECT COUNT(*) FROM report_tasks "
                "WHERE status IN ('RUNNING', 'SUBMITTING', 'NEEDS_REVIEW')"
            )
        ).scalar()
        if inflight_count and inflight_count > 0:
            has_inflight = True

    now = _now()
    if has_inflight:
        recovery_id = str(uuid4())
        bind.execute(
            sa.text(
                "INSERT INTO task_execution_slot ("
                "singleton_id, generation, phase, task_id, operator_account_id, "
                "attempt_id, run_version, command_id, runtime_epoch, admitted_at, "
                "recovery_id, recovery_reason, recovery_started_at"
                ") VALUES ("
                "1, 0, 'RECOVERY_REQUIRED', NULL, NULL, NULL, NULL, NULL, NULL, NULL, "
                ":rec_id, 'LEGACY_INFLIGHT_TASKS', :now"
                ")"
            ),
            {"rec_id": recovery_id, "now": now},
        )
    else:
        bind.execute(
            sa.text(
                "INSERT INTO task_execution_slot ("
                "singleton_id, generation, phase, task_id, operator_account_id, "
                "attempt_id, run_version, command_id, runtime_epoch, admitted_at, "
                "recovery_id, recovery_reason, recovery_started_at"
                ") VALUES ("
                "1, 0, 'FREE', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL"
                ")"
            )
        )
