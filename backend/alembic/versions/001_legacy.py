# File: backend/alembic/versions/001_legacy.py
"""Baseline legacy tables without stamping over or replacing existing data."""
from alembic import op
import sqlalchemy as sa

revision = "001_legacy"
down_revision = None
branch_labels = depends_on = None


def upgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    definitions = {
        "owner_profiles": [
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("full_name", sa.String(255), nullable=False),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("country", sa.String(10), nullable=False),
            sa.Column("organization_name", sa.String(255)),
            sa.Column("created_at", sa.DateTime(timezone=True)),
        ],
        "proxies": [
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("protocol", sa.String(10)), sa.Column("host", sa.String(255), nullable=False),
            sa.Column("port", sa.Integer, nullable=False), sa.Column("country", sa.String(10), nullable=False),
            sa.Column("username", sa.String(255)), sa.Column("password", sa.String(255)),
            sa.Column("status", sa.String(20)), sa.Column("latency_ms", sa.Integer),
            sa.Column("consecutive_failures", sa.Integer),
            sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        ],
        "batch_jobs": [
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("owner_profile_id", sa.String(36), sa.ForeignKey("owner_profiles.id"), nullable=False),
            sa.Column("preferred_country", sa.String(10)), sa.Column("concurrency", sa.Integer),
            sa.Column("delay_min", sa.Integer), sa.Column("delay_max", sa.Integer),
            sa.Column("status", sa.String(20)), sa.Column("created_at", sa.DateTime(timezone=True)),
            sa.Column("completed_at", sa.DateTime(timezone=True)),
        ],
        "report_tasks": [
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("batch_job_id", sa.String(36), sa.ForeignKey("batch_jobs.id"), nullable=False),
            sa.Column("target_url", sa.Text, nullable=False), sa.Column("target_platform", sa.String(50), nullable=False),
            sa.Column("target_content_type", sa.String(50), nullable=False),
            sa.Column("original_url", sa.Text, nullable=False), sa.Column("explanation", sa.Text, nullable=False),
            sa.Column("status", sa.String(20)), sa.Column("retry_count", sa.Integer),
            sa.Column("max_retries", sa.Integer), sa.Column("proxy_id", sa.String(36)),
            sa.Column("meta_case_number", sa.String(100)), sa.Column("screenshot_path", sa.String(500)),
            sa.Column("error_message", sa.Text), sa.Column("infringing_account", sa.String(255)),
            sa.Column("created_at", sa.DateTime(timezone=True)), sa.Column("completed_at", sa.DateTime(timezone=True)),
        ],
    }
    for table, columns in definitions.items():
        if table not in existing:
            op.create_table(table, *columns)
        else:
            found = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}
            required = {column.name for column in columns} - {"infringing_account"}
            if not required <= found:
                raise RuntimeError(f"Legacy schema mismatch in {table}; restore backup and inspect migration.")


def downgrade():
    raise RuntimeError("Legacy baseline downgrade is destructive. Restore a database backup instead.")
