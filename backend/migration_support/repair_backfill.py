# File: backend/migration_support/repair_backfill.py
"""Backfill and account sanitization routines for migration 006."""

import sqlalchemy as sa


def quarantine_default_accounts(bind) -> int:
    """Quarantine any synthetic default accounts so no active dummy users remain."""
    inspector = sa.inspect(bind)
    if "operator_accounts" not in inspector.get_table_names():
        return 0
    res = bind.execute(
        sa.text(
            "UPDATE operator_accounts "
            "SET status = 'QUARANTINED' "
            "WHERE username_key = 'system_default' AND status = 'ACTIVE'"
        )
    )
    return getattr(res, "rowcount", 0)


def backfill_authority_contract_versions(bind) -> None:
    """Ensure existing task_start_receipts carry authority_contract_version = 1."""
    inspector = sa.inspect(bind)
    if "task_start_receipts" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("task_start_receipts")}
    if "authority_contract_version" in cols:
        bind.execute(
            sa.text(
                "UPDATE task_start_receipts "
                "SET authority_contract_version = 1 "
                "WHERE authority_contract_version IS NULL"
            )
        )
