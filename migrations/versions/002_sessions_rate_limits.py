"""sessions and rate_limit_buckets for multi-instance shared state

Revision ID: 002_sessions_rate_limits
Revises: 001_portal_schema
Create Date: 2026-10-28

Flask-Session may create ``sessions`` with checkfirst=True on first boot;
use IF NOT EXISTS so the migrate Job stays safe either way.
"""

from alembic import op
import sqlalchemy as sa

revision = "002_sessions_rate_limits"
down_revision = "001_portal_schema"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id SERIAL NOT NULL PRIMARY KEY,
            session_id VARCHAR(255),
            data BYTEA,
            expiry TIMESTAMP WITHOUT TIME ZONE,
            UNIQUE (session_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sessions_expiry ON sessions (expiry)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS rate_limit_buckets (
            key VARCHAR(255) NOT NULL PRIMARY KEY,
            count INTEGER NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_rate_limit_buckets_expires_at "
        "ON rate_limit_buckets (expires_at)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_rate_limit_buckets_expires_at")
    op.execute("DROP TABLE IF EXISTS rate_limit_buckets")
    op.execute("DROP INDEX IF EXISTS ix_sessions_expiry")
    op.execute("DROP TABLE IF EXISTS sessions")
