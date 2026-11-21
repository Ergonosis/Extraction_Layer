"""Notify + dunning email helpers (no SMTP)."""

from __future__ import annotations

from src.billing.notify import clear_sent_emails, send_billing_email, sent_emails


def test_send_billing_email_logs_when_disabled(monkeypatch):
    monkeypatch.setenv('BILLING_EMAIL_ENABLED', 'false')
    clear_sent_emails()
    ok = send_billing_email(to='a@example.com', subject='Hi', body='Body')
    assert ok is True
    assert len(sent_emails()) == 1
    assert sent_emails()[0]['to'] == 'a@example.com'
    assert sent_emails()[0]['subject'] == 'Hi'


def test_send_billing_email_skips_empty_recipients(monkeypatch):
    monkeypatch.setenv('BILLING_EMAIL_ENABLED', 'false')
    clear_sent_emails()
    assert send_billing_email(to=['', '  '], subject='x', body='y') is False
    assert sent_emails() == []
