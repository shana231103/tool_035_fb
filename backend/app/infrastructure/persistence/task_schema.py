# File: backend/app/infrastructure/persistence/task_schema.py
"""Runtime schema health and integrity checker for standalone task execution."""

from typing import Any, Dict
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession


def _check_task_schema_sync(bind) -> Dict[str, Any]:
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    required = {
        "report_tasks",
        "task_execution_slot",
        "task_start_receipts",
        "task_control_receipts",
        "task_artifact_links",
    }
    missing = required - tables
    if missing:
        raise RuntimeError(f"Database missing required task tables: {missing}")

    cols = {c["name"] for c in inspector.get_columns("report_tasks")}
    required_cols = {"target_urls_json", "version", "name", "status"}
    missing_cols = required_cols - cols
    if missing_cols:
        raise RuntimeError(f"Database missing required report_tasks columns: {missing_cols}")

    slot_row = bind.execute(
        sa.text("SELECT singleton_id, generation, phase FROM task_execution_slot WHERE singleton_id = 1")
    ).fetchone()
    if not slot_row:
        raise RuntimeError("task_execution_slot singleton row (singleton_id=1) is missing.")

    dialect = bind.dialect.name
    if dialect == "sqlite":
        fk_errors = bind.execute(sa.text("PRAGMA foreign_key_check")).fetchall()
        if fk_errors:
            raise RuntimeError(f"Foreign key verification failed: {fk_errors}")

    return {
        "verified": True,
        "slot_phase": slot_row[2],
        "slot_generation": slot_row[1],
    }


def check_task_schema_sync(bind: Any) -> Dict[str, Any]:
    """Synchronous schema health check for migrations and CLI."""
    return _check_task_schema_sync(bind)


async def check_task_schema(target: Any) -> Dict[str, Any]:
    """Verify task execution schema integrity using an async session or connection."""
    if isinstance(target, AsyncSession):
        conn = await target.connection()
        return await conn.run_sync(_check_task_schema_sync)
    elif isinstance(target, AsyncConnection):
        return await target.run_sync(_check_task_schema_sync)
    else:
        return _check_task_schema_sync(target)
