# File: backend/migration_support/operator_004.py
"""Migration support helpers for revision 004 operator accounts."""

from datetime import datetime, timezone
from uuid import uuid4
import sqlalchemy as sa


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_quarantined_account(bind) -> str:
    inspector = sa.inspect(bind)
    if "operator_accounts" not in inspector.get_table_names():
        return str(uuid4())

    existing = bind.execute(
        sa.text("SELECT id FROM operator_accounts WHERE status = 'QUARANTINED' LIMIT 1")
    ).scalar()
    if existing:
        return str(existing)

    quarantine_id = str(uuid4())
    bind.execute(
        sa.text(
            "INSERT INTO operator_accounts (id, username_key, username_display, "
            "password_hash, status, auth_version, run_version, created_at, updated_at) "
            "VALUES (:id, NULL, NULL, NULL, 'QUARANTINED', 1, 1, :now, :now)"
        ),
        {"id": quarantine_id, "now": _now()},
    )
    return quarantine_id


def backfill_legacy_ownership(bind, quarantine_id: str) -> None:
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    for tbl in ("owner_profiles", "proxies", "batch_jobs", "report_tasks"):
        if tbl in tables:
            cols = {c["name"] for c in inspector.get_columns(tbl)}
            if "operator_account_id" in cols:
                bind.execute(
                    sa.text(
                        f"UPDATE {tbl} SET operator_account_id = :qid "
                        "WHERE operator_account_id IS NULL OR operator_account_id = ''"
                    ),
                    {"qid": quarantine_id},
                )

    if "batch_jobs" in tables:
        cols = {c["name"] for c in inspector.get_columns("batch_jobs")}
        if "pause_reason" in cols:
            bind.execute(
                sa.text(
                    "UPDATE batch_jobs SET status = 'PAUSED', "
                    "pause_reason = 'LEGACY_QUARANTINE' "
                    "WHERE status = 'RUNNING' AND operator_account_id = :qid"
                ),
                {"qid": quarantine_id},
            )

    if "proxy_owner_refs" in tables:
        if "proxies" in tables:
            bind.execute(
                sa.text(
                    "INSERT OR IGNORE INTO proxy_owner_refs (proxy_id, operator_account_id) "
                    "SELECT id, operator_account_id FROM proxies "
                    "WHERE operator_account_id IS NOT NULL AND id IS NOT NULL"
                )
            )
        if "report_tasks" in tables:
            bind.execute(
                sa.text(
                    "INSERT OR IGNORE INTO proxy_owner_refs (proxy_id, operator_account_id) "
                    "SELECT proxy_id, operator_account_id FROM report_tasks "
                    "WHERE proxy_id IS NOT NULL AND operator_account_id IS NOT NULL"
                )
            )


def verify_foreign_keys(bind) -> None:
    dialect = bind.dialect.name
    if dialect == "sqlite":
        res = bind.execute(sa.text("PRAGMA foreign_key_check")).fetchall()
        if res:
            raise RuntimeError(f"Foreign key integrity check failed: {res}")
