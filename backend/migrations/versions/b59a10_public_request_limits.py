"""Share bounded request windows between API processes."""

import sqlalchemy as sa
from alembic import op

revision = "b59a10"
down_revision = "ae6709"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("last_maintenance_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_users_last_maintenance_at", "users", ["last_maintenance_at"])
    op.create_table(
        "request_limits",
        sa.Column("key_hash", sa.String(64), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_request_limits_expires_at", "request_limits", ["expires_at"])


def downgrade():
    op.drop_index("ix_request_limits_expires_at", table_name="request_limits")
    op.drop_table("request_limits")
    op.drop_index("ix_users_last_maintenance_at", table_name="users")
    op.drop_column("users", "last_maintenance_at")
