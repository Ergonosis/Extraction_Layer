"""billing hardening: dunning email dedupe + usage ledger outbox

Revision ID: 005_billing_hardening
Revises: 004_billing_schema
Create Date: 2026-11-20
"""

from alembic import op

revision = '005_billing_hardening'
down_revision = '004_billing_schema'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        ALTER TABLE organization_billing
            ADD COLUMN IF NOT EXISTS last_dunning_email_at TIMESTAMP WITH TIME ZONE,
            ADD COLUMN IF NOT EXISTS last_dunning_email_kind VARCHAR(64)
        """
    )

    op.execute(
        """
        ALTER TABLE billing_usage_ledger
            ADD COLUMN IF NOT EXISTS stripe_send_status VARCHAR(16) NOT NULL DEFAULT 'pending',
            ADD COLUMN IF NOT EXISTS stripe_send_attempts INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS last_send_error TEXT,
            ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'ck_billing_usage_ledger_stripe_send_status'
            ) THEN
                ALTER TABLE billing_usage_ledger
                    ADD CONSTRAINT ck_billing_usage_ledger_stripe_send_status
                    CHECK (stripe_send_status IN ('pending', 'sent', 'failed'));
            END IF;
        END $$
        """
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_billing_usage_ledger_outbox '
        'ON billing_usage_ledger (stripe_send_status, next_attempt_at)'
    )
    # Rows that already have a Stripe event id are treated as sent.
    op.execute(
        """
        UPDATE billing_usage_ledger
        SET stripe_send_status = 'sent'
        WHERE stripe_meter_event_id IS NOT NULL
          AND stripe_send_status = 'pending'
        """
    )


def downgrade():
    op.execute('DROP INDEX IF EXISTS ix_billing_usage_ledger_outbox')
    op.execute('ALTER TABLE billing_usage_ledger DROP CONSTRAINT IF EXISTS ck_billing_usage_ledger_stripe_send_status')
    op.execute(
        """
        ALTER TABLE billing_usage_ledger
            DROP COLUMN IF EXISTS next_attempt_at,
            DROP COLUMN IF EXISTS last_send_error,
            DROP COLUMN IF EXISTS stripe_send_attempts,
            DROP COLUMN IF EXISTS stripe_send_status
        """
    )
    op.execute(
        """
        ALTER TABLE organization_billing
            DROP COLUMN IF EXISTS last_dunning_email_kind,
            DROP COLUMN IF EXISTS last_dunning_email_at
        """
    )
