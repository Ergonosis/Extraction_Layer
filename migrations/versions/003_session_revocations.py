"""session_revocations tombstones for monotonic logout

Revision ID: 003_session_revocations
Revises: 002_sessions_rate_limits
Create Date: 2026-11-12
"""

from alembic import op

revision = '003_session_revocations'
down_revision = '002_sessions_rate_limits'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS session_revocations (
            store_id VARCHAR(255) NOT NULL PRIMARY KEY,
            revoked_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
        )
        """
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_session_revocations_expires_at ON session_revocations (expires_at)'
    )


def downgrade():
    op.execute('DROP INDEX IF EXISTS ix_session_revocations_expires_at')
    op.execute('DROP TABLE IF EXISTS session_revocations')
