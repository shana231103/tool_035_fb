# File: backend/alembic_postgres/versions/002_task_start_contract.py
"""Forward task command and archival ownership constraints for PostgreSQL."""
from alembic import op
import sqlalchemy as sa
from migration_support.task_start_contract import START_CHECK, CONTROL_CHECK, audit_existing, verify_preserved

revision = "002_task_start_contract"
down_revision = "001_supabase_runtime"
branch_labels = depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError("This revision requires PostgreSQL.")
    before = audit_existing(bind)
    op.add_column("task_control_receipts", sa.Column("payload_fingerprint", sa.Text(), nullable=True))
    op.add_column("task_control_receipts", sa.Column("expected_task_version", sa.Integer(), nullable=True))
    op.add_column("task_control_receipts", sa.Column("attempt_id", sa.String(36), nullable=True))
    op.add_column("task_control_receipts", sa.Column("authority_contract_version", sa.Integer(), nullable=False, server_default="1"))
    op.create_check_constraint("ck_control_receipt_contract", "task_control_receipts", CONTROL_CHECK)
    op.create_check_constraint("ck_control_receipt_version", "task_control_receipts", "version >= 1")
    op.create_check_constraint("ck_start_receipt_contract", "task_start_receipts", START_CHECK)
    op.create_check_constraint("ck_report_task_version_positive", "report_tasks", "version >= 1")
    op.create_check_constraint("ck_slot_generation_nonnegative", "task_execution_slot", "generation >= 0")
    op.alter_column("operator_artifacts", "job_id", existing_type=sa.String(36), nullable=True)
    op.create_check_constraint("ck_artifact_resource", "operator_artifacts", "job_id IS NOT NULL OR task_id IS NOT NULL")
    op.create_unique_constraint("uq_artifact_owner_kind", "operator_artifacts", ["id", "operator_account_id", "kind"])
    op.create_foreign_key("fk_artifact_task_owner", "operator_artifacts", "report_tasks", ["task_id", "operator_account_id"], ["id", "operator_account_id"])
    op.create_foreign_key("fk_task_artifact_links_artifact_owner_kind", "task_artifact_links", "operator_artifacts", ["artifact_id", "operator_account_id", "kind"], ["id", "operator_account_id", "kind"])
    for table in ("task_control_receipts", "task_start_receipts", "operator_artifacts", "task_artifact_links"):
        bind.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        for role in ("anon", "authenticated"):
            if bind.execute(sa.text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:role)"), {"role": role}).scalar():
                bind.execute(sa.text(f"REVOKE ALL ON TABLE {table} FROM {role}"))
    verify_preserved(bind, before)


def downgrade():
    raise RuntimeError("Restore the pre-migration backup; task-owned artifacts cannot be downgraded safely.")
