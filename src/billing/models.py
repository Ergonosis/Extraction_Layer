"""Billing tables — Stripe IDs and commercial terms only (no card data)."""

from __future__ import annotations

from datetime import UTC, datetime

from src.api.extensions import db


def _utcnow():
    """Shared UTC timestamp helper (also imported by webhook/dunning modules)."""
    return datetime.now(UTC)


class PlatformAdmin(db.Model):
    """Ergonosis staff allowed to use Admin Billing."""

    __tablename__ = 'platform_admins'
    __table_args__ = (
        db.UniqueConstraint('ms_oid', name='uq_platform_admins_ms_oid'),
        db.UniqueConstraint('email', name='uq_platform_admins_email'),
    )

    id = db.Column(db.Integer, primary_key=True)
    ms_oid = db.Column(db.String(36), nullable=True)
    email = db.Column(db.String(320), nullable=True)
    display_name = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)


class OrganizationBilling(db.Model):
    """Per-org commercial terms + Stripe references + entitlement."""

    __tablename__ = 'organization_billing'
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('setup_required', 'active', 'past_due', 'suspended', 'canceled')",
            name='ck_organization_billing_status',
        ),
        db.CheckConstraint("entitlement IN ('enabled', 'suspended')", name='ck_organization_billing_entitlement'),
    )

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False, unique=True, index=True)

    stripe_customer_id = db.Column(db.String(255), nullable=True)
    default_payment_method_id = db.Column(db.String(255), nullable=True)
    stripe_subscription_id = db.Column(db.String(255), nullable=True)

    flat_enabled = db.Column(db.Boolean, nullable=False, default=False)
    exports_enabled = db.Column(db.Boolean, nullable=False, default=False)
    api_calls_enabled = db.Column(db.Boolean, nullable=False, default=False)

    stripe_flat_price_id = db.Column(db.String(255), nullable=True)
    stripe_exports_price_id = db.Column(db.String(255), nullable=True)
    stripe_api_calls_price_id = db.Column(db.String(255), nullable=True)

    included_exports = db.Column(db.Integer, nullable=False, default=0)
    included_api_calls = db.Column(db.Integer, nullable=False, default=0)

    terms_markdown = db.Column(db.Text, nullable=True)
    terms_json = db.Column(db.JSON, nullable=True)

    status = db.Column(db.String(32), nullable=False, default='setup_required')
    past_due_since = db.Column(db.DateTime(timezone=True), nullable=True)
    suspend_after = db.Column(db.DateTime(timezone=True), nullable=True)
    entitlement = db.Column(db.String(32), nullable=False, default='enabled')

    has_open_dispute = db.Column(db.Boolean, nullable=False, default=False)
    dispute_opened_at = db.Column(db.DateTime(timezone=True), nullable=True)

    pm_brand = db.Column(db.String(32), nullable=True)
    pm_last4 = db.Column(db.String(4), nullable=True)
    pm_exp_month = db.Column(db.Integer, nullable=True)
    pm_exp_year = db.Column(db.Integer, nullable=True)

    # Dunning email dedupe (hardening)
    last_dunning_email_at = db.Column(db.DateTime(timezone=True), nullable=True)
    last_dunning_email_kind = db.Column(db.String(64), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class BillingUsageLedger(db.Model):
    """Local usage log; idempotency_key maps to Stripe meter event identifier."""

    __tablename__ = 'billing_usage_ledger'
    __table_args__ = (
        db.UniqueConstraint('idempotency_key', name='uq_billing_usage_ledger_idempotency_key'),
        db.Index('ix_billing_usage_ledger_org_meter', 'organization_id', 'meter'),
        db.Index('ix_billing_usage_ledger_outbox', 'stripe_send_status', 'next_attempt_at'),
        db.CheckConstraint(
            "stripe_send_status IN ('pending', 'sent', 'failed')", name='ck_billing_usage_ledger_stripe_send_status'
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False, index=True)
    meter = db.Column(db.String(64), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    idempotency_key = db.Column(db.String(255), nullable=False)
    stripe_meter_event_id = db.Column(db.String(255), nullable=True)
    stripe_send_status = db.Column(db.String(16), nullable=False, default='pending')
    stripe_send_attempts = db.Column(db.Integer, nullable=False, default=0)
    last_send_error = db.Column(db.Text, nullable=True)
    next_attempt_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)


class StripeWebhookEvent(db.Model):
    """Dedupe store for Stripe webhook event ids."""

    __tablename__ = 'stripe_webhook_events'

    event_id = db.Column(db.String(255), primary_key=True)
    event_type = db.Column(db.String(128), nullable=False)
    processed_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)


class BillingAdminEvent(db.Model):
    """Audit trail for admin billing actions (refunds, plan changes, resume)."""

    __tablename__ = 'billing_admin_events'

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True, index=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action = db.Column(db.String(64), nullable=False)
    detail_json = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_utcnow)
