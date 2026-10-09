"""Add lease fencing and analytical SQL views."""
from alembic import op
import sqlalchemy as sa

revision = "e7281f"
down_revision = "ca50cb3db5e5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("jobs", sa.Column("claim_token", sa.String(36), nullable=True))
    op.execute("""CREATE VIEW scan_risk_metrics AS
        SELECT s.id AS scan_id, s.project_id, s.created_at, s.status,
            COUNT(f.id) AS findings, COALESCE(MAX(f.priority),0) AS maximum_priority,
            SUM(CASE WHEN f.severity='critical' THEN 1 ELSE 0 END) AS critical_count
        FROM scans s LEFT JOIN findings f ON f.scan_id=s.id
        GROUP BY s.id,s.project_id,s.created_at,s.status""")
    op.execute("""CREATE VIEW notification_delivery_metrics AS
        SELECT n.user_id,n.project_id,n.status,COUNT(*) AS events,
            SUM(n.attempts) AS delivery_attempts
        FROM notifications n GROUP BY n.user_id,n.project_id,n.status""")


def downgrade():
    op.execute("DROP VIEW notification_delivery_metrics")
    op.execute("DROP VIEW scan_risk_metrics")
    op.drop_column("jobs", "claim_token")
