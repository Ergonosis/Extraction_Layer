"""billing schema: org billing, usage ledger, webhooks, platform admins

Revision ID: 004_billing_schema
Revises: 003_session_revocations
Create Date: 2026-11-20
"""

from alembic import op

revision = '004_billing_schema'
down_revision = '003_session_revocations'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS platform_admins (
            id SERIAL PRIMARY KEY,
            ms_oid VARCHAR(36),
            email VARCHAR(320),
            display_name VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            CONSTRAINT uq_platform_admins_ms_oid UNIQUE (ms_oid),
            CONSTRAINT uq_platform_admins_email UNIQUE (email)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS organization_billing (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id),
            stripe_customer_id VARCHAR(255),
            default_payment_method_id VARCHAR(255),
            stripe_subscription_id VARCHAR(255),
            flat_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            exports_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            api_calls_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            stripe_flat_price_id VARCHAR(255),
            stripe_exports_price_id VARCHAR(255),
            stripe_api_calls_price_id VARCHAR(255),
            included_exports INTEGER NOT NULL DEFAULT 0,
            included_api_calls INTEGER NOT NULL DEFAULT 0,
            terms_markdown TEXT,
            terms_json JSONB,
            status VARCHAR(32) NOT NULL DEFAULT 'setup_required',
            past_due_since TIMESTAMP WITH TIME ZONE,
            suspend_after TIMESTAMP WITH TIME ZONE,
            entitlement VARCHAR(32) NOT NULL DEFAULT 'enabled',
            has_open_dispute BOOLEAN NOT NULL DEFAULT FALSE,
            dispute_opened_at TIMESTAMP WITH TIME ZONE,
            pm_brand VARCHAR(32),
            pm_last4 VARCHAR(4),
            pm_exp_month INTEGER,
            pm_exp_year INTEGER,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
            CONSTRAINT uq_organization_billing_organization_id UNIQUE (organization_id),
            CONSTRAINT ck_organization_billing_status CHECK (
                status IN ('setup_required', 'active', 'past_due', 'suspended', 'canceled')
            ),
            CONSTRAINT ck_organization_billing_entitlement CHECK (
                entitlement IN ('enabled', 'suspended')
            )
        )
        """
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_organization_billing_organization_id ON organization_billing (organization_id)'
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS billing_usage_ledger (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id),
            meter VARCHAR(64) NOT NULL,
            quantity INTEGER NOT NULL,
            idempotency_key VARCHAR(255) NOT NULL,
            stripe_meter_event_id VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            CONSTRAINT uq_billing_usage_ledger_idempotency_key UNIQUE (idempotency_key)
        )
        """
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_billing_usage_ledger_organization_id ON billing_usage_ledger (organization_id)'
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_billing_usage_ledger_org_meter ON billing_usage_ledger (organization_id, meter)'
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS stripe_webhook_events (
            event_id VARCHAR(255) NOT NULL PRIMARY KEY,
            event_type VARCHAR(128) NOT NULL,
            processed_at TIMESTAMP WITH TIME ZONE NOT NULL
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS billing_admin_events (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER REFERENCES organizations(id),
            actor_user_id INTEGER REFERENCES users(id),
            action VARCHAR(64) NOT NULL,
            detail_json JSONB,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL
        )
        """
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_billing_admin_events_organization_id ON billing_admin_events (organization_id)'
    )


def downgrade():
    op.execute('DROP INDEX IF EXISTS ix_billing_admin_events_organization_id')
    op.execute('DROP TABLE IF EXISTS billing_admin_events')
    op.execute('DROP TABLE IF EXISTS stripe_webhook_events')
    op.execute('DROP INDEX IF EXISTS ix_billing_usage_ledger_org_meter')
    op.execute('DROP INDEX IF EXISTS ix_billing_usage_ledger_organization_id')
    op.execute('DROP TABLE IF EXISTS billing_usage_ledger')
    op.execute('DROP INDEX IF EXISTS ix_organization_billing_organization_id')
    op.execute('DROP TABLE IF EXISTS organization_billing')
    op.execute('DROP TABLE IF EXISTS platform_admins')
