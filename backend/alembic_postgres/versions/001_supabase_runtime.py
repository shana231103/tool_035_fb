# File: backend/alembic_postgres/versions/001_supabase_runtime.py
"""Create a fresh PostgreSQL runtime schema without legacy data migration."""

from pathlib import Path
from alembic import op
import sqlalchemy as sa

revision = "001_supabase_runtime"
down_revision = None
branch_labels = depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError("This baseline requires PostgreSQL.")
    sql_path = Path(__file__).with_name("001_supabase_runtime.sql")
    statements = sql_path.read_text(encoding="utf-8").split(";")
    # A baseline must never adopt existing application tables or their contents.
    existing = set(sa.inspect(bind).get_table_names())
    for statement in statements:
        tokens = statement.strip().split()
        if tokens[:2] == ["CREATE", "TABLE"] and tokens[2] in existing:
            raise RuntimeError("PostgreSQL baseline requires a new empty application database.")
    for statement in statements:
        if statement.strip():
            bind.execute(sa.text(statement))
    bind.execute(sa.text("ALTER TABLE alembic_version ENABLE ROW LEVEL SECURITY"))


def downgrade():
    raise RuntimeError("Runtime tables are not deleted automatically. Restore a backup instead.")
