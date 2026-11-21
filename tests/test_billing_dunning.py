"""Dunning job: reminders while in grace, suspend after suspend_after."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from src.billing.dunning import KIND_REMINDER, KIND_SUSPENDED, run_dunning_pass
from src.billing.notify import clear_sent_emails, sent_emails


def _past_due_row(*, suspend_after, last_kind=None, last_at=None):
    row = MagicMock()
    row.organization_id = 7
    row.status = 'past_due'
    row.entitlement = 'enabled'
    row.suspend_after = suspend_after
    row.last_dunning_email_kind = last_kind
    row.last_dunning_email_at = last_at
    return row


def test_dunning_sends_reminder_while_in_grace(monkeypatch):
    monkeypatch.setenv('BILLING_EMAIL_ENABLED', 'false')
    clear_sent_emails()
    row = _past_due_row(suspend_after=datetime.now(UTC) + timedelta(days=3))

    with (
        patch('src.billing.dunning.db') as mock_db,
        patch('src.billing.dunning.org_billing_emails', return_value=['user@example.com']),
    ):
        mock_db.session.execute.return_value.scalars.return_value.all.return_value = [row]
        out = run_dunning_pass()

    assert out['reminded'] == 1
    assert out['suspended'] == 0
    assert row.last_dunning_email_kind == KIND_REMINDER
    assert any('past due' in e['subject'].lower() for e in sent_emails())


def test_dunning_skips_reminder_within_dedupe_window(monkeypatch):
    monkeypatch.setenv('BILLING_EMAIL_ENABLED', 'false')
    clear_sent_emails()
    row = _past_due_row(
        suspend_after=datetime.now(UTC) + timedelta(days=2),
        last_kind=KIND_REMINDER,
        last_at=datetime.now(UTC) - timedelta(hours=1),
    )

    with (
        patch('src.billing.dunning.db') as mock_db,
        patch('src.billing.dunning.org_billing_emails', return_value=['user@example.com']),
    ):
        mock_db.session.execute.return_value.scalars.return_value.all.return_value = [row]
        out = run_dunning_pass()

    assert out['reminded'] == 0
    assert out['suspended'] == 0
    assert sent_emails() == []


def test_dunning_suspends_after_grace_and_emails(monkeypatch):
    monkeypatch.setenv('BILLING_EMAIL_ENABLED', 'false')
    clear_sent_emails()
    row = _past_due_row(suspend_after=datetime.now(UTC) - timedelta(minutes=1))

    with (
        patch('src.billing.dunning.db') as mock_db,
        patch('src.billing.dunning.org_billing_emails', return_value=['user@example.com']),
    ):
        mock_db.session.execute.return_value.scalars.return_value.all.return_value = [row]
        out = run_dunning_pass()

    assert out['suspended'] == 1
    assert out['reminded'] == 0
    assert row.entitlement == 'suspended'
    assert row.status == 'suspended'
    assert row.last_dunning_email_kind == KIND_SUSPENDED
    assert any('suspended' in e['subject'].lower() for e in sent_emails())
