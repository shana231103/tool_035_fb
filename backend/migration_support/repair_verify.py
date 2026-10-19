# File: backend/migration_support/repair_verify.py
"""Verification routines for migration 006 repair."""

from typing import Any, Dict
import sqlalchemy as sa
from backend.migration_support.repair_manifest import REPAIR_REQUIRED_TABLES


def verify_repair_schema(bind) -> Dict[str, Any]:
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    missing = set(REPAIR_REQUIRED_TABLES) - tables
    if missing:
        raise RuntimeError(f"Missing required tables after 006 repair: {missing}")

    if bind.dialect.name == "sqlite":
        fk_errors = bind.execute(sa.text("PRAGMA foreign_key_check")).fetchall()
        if fk_errors:
            raise RuntimeError(f"Foreign key check failed after 006 repair: {fk_errors}")

    active_dummies = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM operator_accounts "
            "WHERE username_key = 'system_default' AND status = 'ACTIVE'"
        )
    ).scalar() or 0
    if active_dummies > 0:
        raise RuntimeError("Integrity violation: active default dummy user detected after 006.")

    slot = bind.execute(
        sa.text("SELECT singleton_id, generation, phase FROM task_execution_slot WHERE singleton_id = 1")
    ).fetchone()
    if not slot:
        raise RuntimeError("task_execution_slot singleton row missing after 006 repair.")

    return {
        "verified": True,
        "tables_count": len(tables),
        "slot_phase": slot[2],
        "slot_generation": slot[1],
    }
