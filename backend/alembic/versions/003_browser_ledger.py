# File: backend/alembic/versions/003_browser_ledger.py
"""Add durable browser ownership and singleton installation binding."""
from alembic import op
import sqlalchemy as sa

revision = "003_browser_ledger"
down_revision = "002_alignment"
branch_labels = depends_on = None


def upgrade():
    found = set(sa.inspect(op.get_bind()).get_table_names())
    if "browser_runtime_bindings" not in found:
        op.create_table("browser_runtime_bindings",
            sa.Column("singleton_id", sa.Integer, primary_key=True),
            sa.Column("installation_id", sa.String(36), nullable=False),
            sa.Column("provider_binding_id", sa.String(36), nullable=False),
            sa.Column("host_binding_digest", sa.String(128), nullable=False),
            sa.Column("schema_version", sa.Integer, nullable=False),
            sa.CheckConstraint("singleton_id = 1", name="ck_browser_singleton"))
    if "browser_session_leases" not in found:
        op.create_table("browser_session_leases",
            sa.Column("operation_id", sa.String(36), primary_key=True),
            sa.Column("installation_id", sa.String(36), nullable=False),
            sa.Column("provider_binding_id", sa.String(36), nullable=False),
            sa.Column("task_id", sa.String(36), sa.ForeignKey("report_tasks.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("attempt_id", sa.String(36), nullable=False),
            sa.Column("marker_nonce", sa.String(128), nullable=False),
            sa.Column("profile_id", sa.String(128), nullable=True),
            sa.Column("phase", sa.String(32), nullable=False),
            sa.Column("cleanup_state", sa.String(32), nullable=False),
            sa.Column("version", sa.Integer, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("retries", sa.Integer, nullable=False),
            sa.Column("safe_reason", sa.String(64), nullable=True),
            sa.Column("charged", sa.Boolean, nullable=False),
            sa.Column("completion_evidence", sa.String(32), nullable=False),
            sa.Column("audit_reference", sa.String(128), nullable=True),
            sa.UniqueConstraint("installation_id", "task_id", "attempt_id", name="uq_browser_attempt"),
            sa.UniqueConstraint("provider_binding_id", "profile_id", name="uq_browser_profile"),
            sa.CheckConstraint("version >= 0 AND retries >= 0", name="ck_browser_counters"),
            sa.CheckConstraint("(phase = 'CLOSED' AND charged = false AND cleanup_state = 'CONFIRMED' AND completion_evidence <> 'UNKNOWN') OR (phase <> 'CLOSED' AND charged = true)", name="ck_browser_charge"))
        op.create_index("ix_browser_installation_charge", "browser_session_leases", ["installation_id", "charged", "updated_at"])
        op.create_index("ix_browser_task_charge", "browser_session_leases", ["installation_id", "task_id", "charged"])


def downgrade():
    raise RuntimeError("Browser ownership history cannot be discarded. Stop runtime and restore the pre-upgrade backup.")
