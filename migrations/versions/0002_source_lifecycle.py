"""增加手册退役时间与显式替换导入操作标识。"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("document", sa.Column("retired_at", sa.DateTime(timezone=True)))
    op.add_column("ingest_run", sa.Column("operation", sa.Text(), nullable=False, server_default="append"))
    op.create_check_constraint(op.f("ck_ingest_run_operation"), "ingest_run", "operation IN ('append', 'replace')")


def downgrade():
    op.drop_constraint(op.f("ck_ingest_run_operation"), "ingest_run", type_="check")
    op.drop_column("ingest_run", "operation")
    op.drop_column("document", "retired_at")
