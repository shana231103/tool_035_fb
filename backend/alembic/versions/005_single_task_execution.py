# File: backend/alembic/versions/005_single_task_execution.py
"""Single task execution: standalone ReportTask, global execution slot, receipts, and links."""

from alembic import op
import sqlalchemy as sa

try:
    from migration_support.single_task_schema import (
        create_standalone_task_tables,
        rebuild_report_tasks_table,
    )
    from migration_support.single_task_backfill import (
        backfill_task_artifact_links,
        initialize_execution_slot,
    )
    from migration_support.single_task_verify import (
        verify_single_task_schema,
    )
except ImportError:
    from backend.migration_support.single_task_schema import (
        create_standalone_task_tables,
        rebuild_report_tasks_table,
    )
    from backend.migration_support.single_task_backfill import (
        backfill_task_artifact_links,
        initialize_execution_slot,
    )
    from backend.migration_support.single_task_verify import (
        verify_single_task_schema,
    )

revision = "005_single_task_execution"
down_revision = "004_operator_accounts"
branch_labels = depends_on = None


def upgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        # Capture foreign_keys setting and turn OFF during rebuild
        bind.execute(sa.text("PRAGMA foreign_keys = OFF"))

    # 1. Rebuild report_tasks table
    rebuild_report_tasks_table(bind)

    # 2. Create standalone task execution tables
    create_standalone_task_tables(bind)

    # 3. Backfill artifact links and initialize singleton execution slot
    backfill_task_artifact_links(bind)
    initialize_execution_slot(bind)

    if dialect == "sqlite":
        bind.execute(sa.text("PRAGMA foreign_keys = ON"))

    # 4. Final verification
    verify_single_task_schema(bind)


def downgrade():
    bind = op.get_bind()
    for tbl in (
        "task_artifact_links",
        "task_control_receipts",
        "task_start_receipts",
        "task_execution_slot",
    ):
        op.drop_table(tbl)
