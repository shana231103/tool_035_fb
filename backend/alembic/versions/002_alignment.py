# File: backend/alembic/versions/002_alignment.py
"""Add explicit profile and attempt metadata; never infer legal fields or store OTP."""
from alembic import op
import sqlalchemy as sa

revision = "002_alignment"
down_revision = "001_legacy"
branch_labels = depends_on = None


def alignment_columns():
    return {
        "owner_profiles": [sa.Column(name, sa.String(255), nullable=True) for name in
            ("rights_owner_name", "sender_name", "rights_jurisdiction", "owner_role")],
        "report_tasks": [
            sa.Column("attempt_id", sa.String(36), nullable=True),
            sa.Column("input_snapshot", sa.JSON, nullable=True),
            sa.Column("verification", sa.JSON, nullable=True),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("receipt_text", sa.Text, nullable=True),
            sa.Column("infringing_account", sa.String(255), nullable=True),
        ],
    }


def upgrade():
    for table, columns in alignment_columns().items():
        found = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}
        for column in columns:
            if column.name not in found:
                op.add_column(table, column)


def downgrade():
    raise RuntimeError("Downgrade would discard attempt evidence. Stop workers and restore the pre-upgrade backup.")
