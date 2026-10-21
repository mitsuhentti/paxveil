"""Create operational schema"""
import sqlalchemy as sa
from alembic import op

revision = 'ca50cb3db5e5'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('advisories',
    sa.Column('id', sa.String(length=100), nullable=False),
    sa.Column('aliases', sa.JSON(), nullable=False),
    sa.Column('data', sa.JSON(), nullable=False),
    sa.Column('modified', sa.String(length=60), nullable=True),
    sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('packages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('ecosystem', sa.String(length=16), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('users',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('username', sa.String(length=64), nullable=False),
    sa.Column('password', sa.Text(), nullable=True),
    sa.Column('telegram_id', sa.String(length=24), nullable=True),
    sa.Column('preferences', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('telegram_id'),
    sa.UniqueConstraint('username')
    )
    op.create_table('package_versions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('package_id', sa.Integer(), nullable=False),
    sa.Column('version', sa.String(length=100), nullable=False),
    sa.ForeignKeyConstraint(['package_id'], ['packages.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('package_id', 'version')
    )
    op.create_table('projects',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('filename', sa.String(length=40), nullable=False),
    sa.Column('content', sa.LargeBinary(), nullable=False),
    sa.Column('python_version', sa.String(length=8), nullable=False),
    sa.Column('platform', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_projects_user_id'), 'projects', ['user_id'], unique=False)
    op.create_table('sessions',
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('token_hash')
    )
    op.create_index(op.f('ix_sessions_expires_at'), 'sessions', ['expires_at'], unique=False)
    op.create_index(op.f('ix_sessions_user_id'), 'sessions', ['user_id'], unique=False)
    op.create_table('telegram_link_codes',
    sa.Column('code_hash', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('code_hash')
    )
    op.create_table('finding_states',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('advisory_id', sa.String(length=100), nullable=False),
    sa.Column('package', sa.String(length=200), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id', 'advisory_id', 'package')
    )
    op.create_table('notifications',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('event_key', sa.String(length=64), nullable=False),
    sa.Column('category', sa.String(length=24), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('run_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('lease_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('event_key')
    )
    op.create_index('ix_notifications_due', 'notifications', ['status', 'run_at'], unique=False)
    op.create_index(op.f('ix_notifications_status'), 'notifications', ['status'], unique=False)
    op.create_index(op.f('ix_notifications_user_id'), 'notifications', ['user_id'], unique=False)
    op.create_table('scans',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('report', sa.JSON(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_scans_created_at'), 'scans', ['created_at'], unique=False)
    op.create_index(op.f('ix_scans_project_id'), 'scans', ['project_id'], unique=False)
    op.create_table('subscriptions',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('next_check', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('project_id')
    )
    op.create_index(op.f('ix_subscriptions_next_check'), 'subscriptions', ['next_check'], unique=False)
    op.create_table('delivery_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('notification_id', sa.String(length=36), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('detail', sa.String(length=200), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['notification_id'], ['notifications.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_delivery_logs_notification_id'), 'delivery_logs', ['notification_id'], unique=False)
    op.create_table('finding_status_history',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('state_id', sa.Integer(), nullable=False),
    sa.Column('old_status', sa.String(length=20), nullable=False),
    sa.Column('new_status', sa.String(length=20), nullable=False),
    sa.Column('changed_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['state_id'], ['finding_states.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('findings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('scan_id', sa.String(length=36), nullable=False),
    sa.Column('advisory_id', sa.String(length=100), nullable=False),
    sa.Column('package', sa.String(length=200), nullable=False),
    sa.Column('version', sa.String(length=100), nullable=False),
    sa.Column('priority', sa.Integer(), nullable=False),
    sa.Column('severity', sa.String(length=16), nullable=False),
    sa.ForeignKeyConstraint(['advisory_id'], ['advisories.id'], ),
    sa.ForeignKeyConstraint(['scan_id'], ['scans.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('scan_id', 'advisory_id', 'package', 'version')
    )
    op.create_index(op.f('ix_findings_scan_id'), 'findings', ['scan_id'], unique=False)
    op.create_table('jobs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('project_id', sa.String(length=36), nullable=True),
    sa.Column('scan_id', sa.String(length=36), nullable=True),
    sa.Column('kind', sa.String(length=24), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('run_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('lease_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('result', sa.JSON(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['scan_id'], ['scans.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_jobs_due', 'jobs', ['status', 'run_at'], unique=False)
    op.create_index(op.f('ix_jobs_project_id'), 'jobs', ['project_id'], unique=False)
    op.create_index(op.f('ix_jobs_run_at'), 'jobs', ['run_at'], unique=False)
    op.create_index(op.f('ix_jobs_status'), 'jobs', ['status'], unique=False)
    op.create_index(op.f('ix_jobs_user_id'), 'jobs', ['user_id'], unique=False)
    op.create_table('scan_dependencies',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('scan_id', sa.String(length=36), nullable=False),
    sa.Column('version_id', sa.Integer(), nullable=False),
    sa.Column('direct', sa.Boolean(), nullable=True),
    sa.Column('source', sa.String(length=32), nullable=False),
    sa.ForeignKeyConstraint(['scan_id'], ['scans.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['version_id'], ['package_versions.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('scan_id', 'version_id')
    )
    op.create_index(op.f('ix_scan_dependencies_scan_id'), 'scan_dependencies', ['scan_id'], unique=False)
    op.create_table('source_snapshots',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('scan_id', sa.String(length=36), nullable=False),
    sa.Column('source', sa.String(length=40), nullable=False),
    sa.Column('data', sa.JSON(), nullable=False),
    sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['scan_id'], ['scans.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('fixlab_scenarios',
    sa.Column('job_id', sa.String(length=36), nullable=False),
    sa.Column('scan_id', sa.String(length=36), nullable=False),
    sa.Column('report', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['scan_id'], ['scans.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('job_id')
    )

def downgrade():
    op.drop_table('fixlab_scenarios')
    op.drop_table('source_snapshots')
    op.drop_index(op.f('ix_scan_dependencies_scan_id'), table_name='scan_dependencies')
    op.drop_table('scan_dependencies')
    op.drop_index(op.f('ix_jobs_user_id'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_status'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_run_at'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_project_id'), table_name='jobs')
    op.drop_index('ix_jobs_due', table_name='jobs')
    op.drop_table('jobs')
    op.drop_index(op.f('ix_findings_scan_id'), table_name='findings')
    op.drop_table('findings')
    op.drop_table('finding_status_history')
    op.drop_index(op.f('ix_delivery_logs_notification_id'), table_name='delivery_logs')
    op.drop_table('delivery_logs')
    op.drop_index(op.f('ix_subscriptions_next_check'), table_name='subscriptions')
    op.drop_table('subscriptions')
    op.drop_index(op.f('ix_scans_project_id'), table_name='scans')
    op.drop_index(op.f('ix_scans_created_at'), table_name='scans')
    op.drop_table('scans')
    op.drop_index(op.f('ix_notifications_user_id'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_status'), table_name='notifications')
    op.drop_index('ix_notifications_due', table_name='notifications')
    op.drop_table('notifications')
    op.drop_table('finding_states')
    op.drop_table('telegram_link_codes')
    op.drop_index(op.f('ix_sessions_user_id'), table_name='sessions')
    op.drop_index(op.f('ix_sessions_expires_at'), table_name='sessions')
    op.drop_table('sessions')
    op.drop_index(op.f('ix_projects_user_id'), table_name='projects')
    op.drop_table('projects')
    op.drop_table('package_versions')
    op.drop_table('users')
    op.drop_table('packages')
    op.drop_table('advisories')
