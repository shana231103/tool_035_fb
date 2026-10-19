# File: backend/alembic/versions/007_task_start_contract.py
"""Versioned command contracts and task-owned artifacts; preserve historical data."""
from alembic import op
import sqlalchemy as sa
from migration_support.task_start_contract import START_CHECK, CONTROL_CHECK, audit_existing, verify_preserved

revision = "007_task_start_contract"
down_revision = "006_single_task_repair"
branch_labels = depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        raise RuntimeError("This revision requires SQLite.")
    # Parent-table rebuilds require the exclusive migration connection to enter
    # with enforcement disabled; toggling inside a transaction is ineffective.
    if bind.execute(sa.text("PRAGMA foreign_keys")).scalar():
        raise RuntimeError("Use an exclusive migration connection with foreign_keys disabled before its transaction; the revision verifies all foreign keys afterwards.")
    before = audit_existing(bind)
    with op.batch_alter_table("task_control_receipts", recreate="always") as batch:
        batch.add_column(sa.Column("payload_fingerprint", sa.Text(), nullable=True))
        batch.add_column(sa.Column("expected_task_version", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("attempt_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("authority_contract_version", sa.Integer(), nullable=False, server_default="1"))
        batch.create_check_constraint("ck_control_receipt_contract", CONTROL_CHECK)
        batch.create_check_constraint("ck_control_receipt_version", "version >= 1")
    with op.batch_alter_table("task_start_receipts", recreate="always") as batch:
        batch.create_check_constraint("ck_start_receipt_contract", START_CHECK)
    with op.batch_alter_table("report_tasks", recreate="always") as batch:
        batch.create_check_constraint("ck_report_task_version_positive", "version >= 1")
    with op.batch_alter_table("task_execution_slot", recreate="always",
            table_args=(sa.CheckConstraint("singleton_id = 1", name="ck_task_execution_slot_singleton"),)) as batch:
        batch.create_check_constraint("ck_slot_generation_nonnegative", "generation >= 0")
    with op.batch_alter_table("operator_artifacts", recreate="always") as batch:
        batch.alter_column("job_id", existing_type=sa.String(36), nullable=True)
        batch.create_check_constraint("ck_artifact_resource", "job_id IS NOT NULL OR task_id IS NOT NULL")
        batch.create_unique_constraint("uq_artifact_owner_kind", ["id", "operator_account_id", "kind"])
        batch.create_foreign_key("fk_artifact_task_owner", "report_tasks", ["task_id", "operator_account_id"], ["id", "operator_account_id"])
    with op.batch_alter_table("task_artifact_links", recreate="always") as batch:
        batch.create_foreign_key("fk_task_artifact_links_artifact_owner_kind", "operator_artifacts", ["artifact_id", "operator_account_id", "kind"], ["id", "operator_account_id", "kind"])
    verify_preserved(bind, before)


def downgrade():
    raise RuntimeError("Restore the pre-migration backup; task-owned artifacts cannot be downgraded safely.")
