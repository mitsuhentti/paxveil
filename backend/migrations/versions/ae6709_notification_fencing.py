"""Fence notification delivery leases."""
import sqlalchemy as sa
from alembic import op

revision = "ae6709"
down_revision = "e7281f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("notifications", sa.Column("claim_token", sa.String(36), nullable=True))
    op.execute("UPDATE scans SET report=NULL WHERE CAST(report AS TEXT)='null'")


def downgrade():
    op.drop_column("notifications", "claim_token")
