"""Outbound billing email — log-only unless BILLING_EMAIL_ENABLED=true."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from src.billing.settings import (
    billing_email_enabled,
    billing_email_from,
    billing_smtp_host,
    billing_smtp_password,
    billing_smtp_port,
    billing_smtp_use_tls,
    billing_smtp_user,
)

logger = logging.getLogger(__name__)

# In-memory sink for tests when email is disabled (or always append a copy).
_SENT: list[dict[str, str]] = []


def clear_sent_emails() -> None:
    _SENT.clear()


def sent_emails() -> list[dict[str, str]]:
    return list(_SENT)


def send_billing_email(*, to: str | list[str], subject: str, body: str) -> bool:
    """Send plain-text billing email. Returns True if accepted (or logged in mock)."""
    recipients = [to] if isinstance(to, str) else [r for r in to if r]
    recipients = [r.strip() for r in recipients if r and str(r).strip()]
    if not recipients:
        logger.warning('billing.notify skipped: no recipients subject=%s', subject)
        return False

    record = {'to': ','.join(recipients), 'subject': subject, 'body': body}
    _SENT.append(record)

    if not billing_email_enabled():
        logger.info('billing.notify MOCK to=%s subject=%s\n%s', record['to'], subject, body)
        return True

    host = billing_smtp_host()
    from_addr = billing_email_from()
    if not host or not from_addr:
        logger.error('billing.notify: SMTP host/from required when BILLING_EMAIL_ENABLED=true')
        return False

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = from_addr
    msg['To'] = ', '.join(recipients)
    msg.set_content(body)

    try:
        with smtplib.SMTP(host, billing_smtp_port(), timeout=30) as smtp:
            if billing_smtp_use_tls():
                smtp.starttls()
            user = billing_smtp_user()
            password = billing_smtp_password()
            if user:
                smtp.login(user, password)
            smtp.send_message(msg)
        logger.info('billing.notify sent to=%s subject=%s', record['to'], subject)
        return True
    except Exception:
        logger.exception('billing.notify SMTP failed to=%s subject=%s', record['to'], subject)
        return False
