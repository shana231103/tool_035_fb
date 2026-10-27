# File: backend/alembic/versions/004_bulk_order_import.py
"""Durable import identity, immutable mail assignment and dispatch revision."""
from alembic import op
import sqlalchemy as sa

revision = "004_bulk_order_import"
down_revision = "003_browser_ledger"
branch_labels = depends_on = None

JOB_COLUMNS = (
    ("bulk_import_id", sa.String(36)), ("bulk_import_version", sa.Integer),
    ("bulk_request_sha256", sa.String(64)), ("bulk_content_sha256", sa.String(64)),
    ("bulk_profile_sha256", sa.String(64)), ("bulk_mail_pool", sa.JSON(none_as_null=True)),
    ("bulk_revision", sa.Integer), ("bulk_last_acceptance", sa.JSON(none_as_null=True)),
    ("bulk_pause_reason", sa.String(64)),
)
TASK_COLUMNS = (("bulk_sequence", sa.Integer), ("bulk_source_line", sa.Integer),
                ("assigned_mail_email", sa.String(255)), ("waiting_reason", sa.String(64)))
JOB_CHECK = """(bulk_import_id IS NULL AND bulk_import_version IS NULL AND bulk_request_sha256 IS NULL
    AND bulk_content_sha256 IS NULL AND bulk_profile_sha256 IS NULL AND bulk_mail_pool IS NULL
    AND bulk_revision IS NULL AND bulk_last_acceptance IS NULL AND bulk_pause_reason IS NULL) OR
    (bulk_import_id IS NOT NULL AND bulk_import_version IS NOT NULL AND bulk_import_version = 1
    AND bulk_request_sha256 IS NOT NULL AND length(bulk_request_sha256) = 64
    AND bulk_content_sha256 IS NOT NULL AND length(bulk_content_sha256) = 64
    AND bulk_profile_sha256 IS NOT NULL AND length(bulk_profile_sha256) = 64
    AND bulk_mail_pool IS NOT NULL AND bulk_revision IS NOT NULL AND bulk_revision >= 1)"""
TASK_CHECK = """(bulk_sequence IS NULL AND bulk_source_line IS NULL AND assigned_mail_email IS NULL) OR
    (bulk_sequence IS NOT NULL AND bulk_source_line IS NOT NULL AND bulk_sequence >= 1
    AND bulk_sequence <= 1000 AND bulk_source_line >= 1 AND assigned_mail_email IS NOT NULL)"""


def upgrade():
    with op.batch_alter_table("batch_jobs") as batch:
        for name, kind in JOB_COLUMNS:
            batch.add_column(sa.Column(name, kind, nullable=True))
        batch.create_unique_constraint("uq_bulk_import_id", ["bulk_import_id"])
        batch.create_index("ix_batch_jobs_bulk_content_sha256", ["bulk_content_sha256"])
        batch.create_check_constraint("ck_bulk_job_metadata", JOB_CHECK)
    with op.batch_alter_table("report_tasks") as batch:
        for name, kind in TASK_COLUMNS:
            batch.add_column(sa.Column(name, kind, nullable=True))
        batch.add_column(sa.Column("dispatch_revision", sa.Integer, nullable=False, server_default="0"))
        batch.create_unique_constraint("uq_bulk_task_sequence", ["batch_job_id", "bulk_sequence"])
        batch.create_check_constraint("ck_bulk_task_assignment", TASK_CHECK)
        batch.create_check_constraint("ck_task_dispatch_revision", "dispatch_revision >= 0")
        batch.create_index("ix_task_dispatch_candidates", ["batch_job_id", "status", "bulk_sequence", "id"])


def downgrade():
    connection = op.get_bind()
    populated = connection.scalar(sa.text("SELECT count(*) FROM batch_jobs WHERE bulk_import_id IS NOT NULL"))
    assigned = connection.scalar(sa.text("SELECT count(*) FROM report_tasks WHERE bulk_sequence IS NOT NULL"))
    if populated or assigned:
        raise RuntimeError("Bulk imports require preserved assignments. Restore the pre-upgrade backup instead.")
    with op.batch_alter_table("report_tasks") as batch:
        batch.drop_index("ix_task_dispatch_candidates")
        batch.drop_constraint("uq_bulk_task_sequence", type_="unique")
        batch.drop_constraint("ck_bulk_task_assignment", type_="check")
        batch.drop_constraint("ck_task_dispatch_revision", type_="check")
        for name in [item[0] for item in TASK_COLUMNS] + ["dispatch_revision"]:
            batch.drop_column(name)
    with op.batch_alter_table("batch_jobs") as batch:
        batch.drop_index("ix_batch_jobs_bulk_content_sha256")
        batch.drop_constraint("uq_bulk_import_id", type_="unique")
        batch.drop_constraint("ck_bulk_job_metadata", type_="check")
        for name, _ in JOB_COLUMNS:
            batch.drop_column(name)
