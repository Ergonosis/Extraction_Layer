"""Billing / Stripe runtime settings (env-driven)."""

from __future__ import annotations

import os

from src.api.config import _env_bool, _load_secret


def stripe_enabled() -> bool:
    """Master switch: false → mock adapter (no Stripe network calls)."""
    return _env_bool('STRIPE_ENABLED', False)


def stripe_secret_key() -> str:
    return _load_secret('STRIPE_SECRET_KEY', '') or os.getenv('STRIPE_SECRET_KEY', '')


def stripe_test_mode() -> bool:
    """True when using Stripe test/sandbox secret keys (sk_test_…)."""
    return stripe_secret_key().startswith('sk_test_')


def stripe_publishable_key() -> str:
    return os.getenv('STRIPE_PUBLISHABLE_KEY', '')


def stripe_webhook_secret() -> str:
    return _load_secret('STRIPE_WEBHOOK_SECRET', '') or os.getenv('STRIPE_WEBHOOK_SECRET', '')


def stripe_meter_event_name(meter: str) -> str:
    """Billing Meter event_name configured in Stripe Dashboard."""
    defaults = {'exports': 'exports', 'api_calls': 'api_calls'}
    env_key = {'exports': 'STRIPE_METER_EVENT_EXPORTS', 'api_calls': 'STRIPE_METER_EVENT_API_CALLS'}.get(meter)
    if env_key:
        return os.getenv(env_key, defaults.get(meter, meter)).strip() or defaults.get(meter, meter)
    return meter


def grace_days() -> int:
    try:
        return max(1, int(os.getenv('BILLING_PAST_DUE_GRACE_DAYS', '5')))
    except ValueError:
        return 5


def portal_base_url() -> str:
    return (os.getenv('PORTAL_URL') or 'http://localhost:5175').rstrip('/')


def billing_email_enabled() -> bool:
    return _env_bool('BILLING_EMAIL_ENABLED', False)


def billing_smtp_host() -> str:
    return os.getenv('BILLING_SMTP_HOST', '').strip()


def billing_smtp_port() -> int:
    try:
        return int(os.getenv('BILLING_SMTP_PORT', '587') or '587')
    except ValueError:
        return 587


def billing_smtp_user() -> str:
    return os.getenv('BILLING_SMTP_USER', '').strip()


def billing_smtp_password() -> str:
    return _load_secret('BILLING_SMTP_PASSWORD', '') or os.getenv('BILLING_SMTP_PASSWORD', '')


def billing_smtp_use_tls() -> bool:
    return _env_bool('BILLING_SMTP_USE_TLS', True)


def billing_email_from() -> str:
    return os.getenv('BILLING_EMAIL_FROM', '').strip()


def platform_admin_notify_emails() -> list[str]:
    """Emails for dispute alerts: env allowlist + later merged with DB in callers."""
    raw = os.getenv('PLATFORM_ADMIN_EMAILS', '')
    return [p.strip() for p in raw.split(',') if p.strip()]
