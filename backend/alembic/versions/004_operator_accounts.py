# File: backend/alembic/versions/004_operator_accounts.py
"""Add operator accounts, sessions, tenancy ownership, and artifact tables."""

from alembic import op
import sqlalchemy as sa
try:
    from migration_support.operator_004 import (
        backfill_legacy_ownership,
        create_quarantined_account,
        verify_foreign_keys,
    )
except ImportError:
    from backend.migration_support.operator_004 import (
        backfill_legacy_ownership,
        create_quarantined_account,
        verify_foreign_keys,
    )

revision = "004_operator_accounts"
down_revision = "003_browser_ledger"
branch_labels = depends_on = None


def _add_owner_cols(tbl: str, uq: str, qid: str, extra=()):
    with op.batch_alter_table(tbl) as bop:
        bop.add_column(
            sa.Column(
                "operator_account_id",
                sa.String(36),
                nullable=False,
                server_default=qid,
            )
        )
        bop.create_unique_constraint(uq, ["id", "operator_account_id"])
        for col in extra:
            bop.add_column(col)


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    found = set(inspector.get_table_names())

    if "operator_accounts" not in found:
        op.create_table(
            "operator_accounts",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("username_key", sa.String(64), nullable=True, unique=True),
            sa.Column("username_display", sa.String(64), nullable=True),
            sa.Column("password_hash", sa.String(255), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
            sa.Column("auth_version", sa.Integer, nullable=False, server_default="1"),
            sa.Column("run_version", sa.Integer, nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("auth_version >= 1", name="ck_operator_auth_version"),
            sa.CheckConstraint("run_version >= 1", name="ck_operator_run_version"),
        )
        op.create_index(
            "ix_operator_accounts_username_key",
            "operator_accounts",
            ["username_key"],
            unique=True,
        )

    if "operator_sessions" not in found:
        op.create_table(
            "operator_sessions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("secret_digest", sa.LargeBinary(32), nullable=False, unique=True),
            sa.Column(
                "operator_id",
                sa.String(36),
                sa.ForeignKey("operator_accounts.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("auth_version", sa.Integer, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_operator_sessions_digest",
            "operator_sessions",
            ["secret_digest"],
            unique=True,
        )
        op.create_index(
            "ix_operator_sessions_operator", "operator_sessions", ["operator_id"]
        )
        op.create_index(
            "ix_operator_sessions_expires", "operator_sessions", ["expires_at"]
        )

    if "proxy_owner_refs" not in found:
        op.create_table(
            "proxy_owner_refs",
            sa.Column("proxy_id", sa.String(36), primary_key=True),
            sa.Column(
                "operator_account_id",
                sa.String(36),
                sa.ForeignKey("operator_accounts.id", ondelete="RESTRICT"),
                primary_key=True,
            ),
        )
        op.create_index(
            "ix_proxy_owner_refs_account",
            "proxy_owner_refs",
            ["operator_account_id"],
        )

    if "operator_artifacts" not in found:
        op.create_table(
            "operator_artifacts",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "operator_account_id",
                sa.String(36),
                sa.ForeignKey("operator_accounts.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("job_id", sa.String(36), nullable=False),
            sa.Column("task_id", sa.String(36), nullable=True),
            sa.Column("kind", sa.String(20), nullable=False),
            sa.Column("storage_key", sa.String(255), nullable=False, unique=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_operator_artifacts_key",
            "operator_artifacts",
            ["storage_key"],
            unique=True,
        )
        op.create_index(
            "ix_operator_artifacts_scope",
            "operator_artifacts",
            ["operator_account_id", "job_id"],
        )

    quarantine_id = create_quarantined_account(bind)

    if "owner_profiles" in found:
        if "operator_account_id" not in {c["name"] for c in inspector.get_columns("owner_profiles")}:
            _add_owner_cols("owner_profiles", "uq_owner_profiles_owner", quarantine_id)

    if "proxies" in found:
        cols = {c["name"] for c in inspector.get_columns("proxies")}
        if "operator_account_id" not in cols:
            extra = [sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)] if "deleted_at" not in cols else []
            _add_owner_cols("proxies", "uq_proxies_owner", quarantine_id, extra)

    if "batch_jobs" in found:
        cols = {c["name"] for c in inspector.get_columns("batch_jobs")}
        if "operator_account_id" not in cols:
            extra = [
                sa.Column("execution_run_version", sa.Integer, nullable=False, server_default="1"),
                sa.Column("pause_reason", sa.String(50), nullable=True),
            ]
            _add_owner_cols("batch_jobs", "uq_batch_jobs_owner", quarantine_id, extra)

    if "report_tasks" in found:
        if "operator_account_id" not in {c["name"] for c in inspector.get_columns("report_tasks")}:
            _add_owner_cols("report_tasks", "uq_report_tasks_owner", quarantine_id)

    backfill_legacy_ownership(bind, quarantine_id)
    verify_foreign_keys(bind)


def downgrade():
    raise RuntimeError(
        "Operator tenancy and ownership data cannot be discarded. "
        "Stop runtime and restore the pre-upgrade backup."
    )
