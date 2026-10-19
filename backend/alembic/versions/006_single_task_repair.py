# File: backend/alembic/versions/006_single_task_repair.py
"""Single task repair: forward migration to 006 for full authority & schema repair."""

from alembic import op
import sqlalchemy as sa

try:
    from migration_support.repair_schema import (
        create_legacy_task_metadata_table,
        repair_task_start_receipts,
        repair_task_control_receipts,
    )
    from migration_support.repair_backfill import (
        quarantine_default_accounts,
        backfill_authority_contract_versions,
    )
    from migration_support.repair_verify import verify_repair_schema
except ImportError:
    from backend.migration_support.repair_schema import (
        create_legacy_task_metadata_table,
        repair_task_start_receipts,
        repair_task_control_receipts,
    )
    from backend.migration_support.repair_backfill import (
        quarantine_default_accounts,
        backfill_authority_contract_versions,
    )
    from backend.migration_support.repair_verify import verify_repair_schema

revision = "006_single_task_repair"
down_revision = "005_single_task_execution"
branch_labels = depends_on = None


def upgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        bind.execute(sa.text("PRAGMA foreign_keys = OFF"))

    create_legacy_task_metadata_table(bind)
    repair_task_start_receipts(bind)
    repair_task_control_receipts(bind)
    quarantine_default_accounts(bind)
    backfill_authority_contract_versions(bind)

    if dialect == "sqlite":
        bind.execute(sa.text("PRAGMA foreign_keys = ON"))

    verify_repair_schema(bind)


def downgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "legacy_task_metadata" in tables:
        op.drop_table("legacy_task_metadata")
