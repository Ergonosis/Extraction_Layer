"""Unit tests for platform admin allowlist matching."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.billing.admins import bootstrap_admin_emails, bootstrap_admin_oids, is_platform_admin


def test_bootstrap_admin_emails_parses_csv(monkeypatch):
    monkeypatch.setenv('PLATFORM_ADMIN_EMAILS', 'Alice@Ergonosis.com, bob@ergonosis.com')
    assert bootstrap_admin_emails() == {'alice@ergonosis.com', 'bob@ergonosis.com'}


def test_bootstrap_admin_oids_parses_csv(monkeypatch):
    monkeypatch.setenv('PLATFORM_ADMIN_MS_OIDS', 'AAA-BBB, ccc-ddd')
    assert bootstrap_admin_oids() == {'aaa-bbb', 'ccc-ddd'}


def test_is_platform_admin_via_env_email(monkeypatch):
    monkeypatch.setenv('PLATFORM_ADMIN_EMAILS', 'dante@ergonosis.com')
    monkeypatch.delenv('PLATFORM_ADMIN_MS_OIDS', raising=False)
    with patch('src.billing.admins.db') as mock_db:
        mock_db.session.execute.return_value.scalars.return_value.all.return_value = []
        assert is_platform_admin(email='Dante@Ergonosis.com') is True
        assert is_platform_admin(email='other@ergonosis.com') is False


def test_is_platform_admin_via_env_oid(monkeypatch):
    monkeypatch.delenv('PLATFORM_ADMIN_EMAILS', raising=False)
    monkeypatch.setenv('PLATFORM_ADMIN_MS_OIDS', '1111-2222')
    with patch('src.billing.admins.db') as mock_db:
        mock_db.session.execute.return_value.scalars.return_value.all.return_value = []
        assert is_platform_admin(ms_oid='1111-2222') is True
        assert is_platform_admin(ms_oid='9999') is False


def test_is_platform_admin_via_table_row(monkeypatch):
    monkeypatch.delenv('PLATFORM_ADMIN_EMAILS', raising=False)
    monkeypatch.delenv('PLATFORM_ADMIN_MS_OIDS', raising=False)
    row = MagicMock()
    row.ms_oid = 'abcd-efgh'
    row.email = 'staff@ergonosis.com'
    with patch('src.billing.admins.db') as mock_db:
        mock_db.session.execute.return_value.scalars.return_value.all.return_value = [row]
        assert is_platform_admin(ms_oid='ABCD-EFGH') is True
        assert is_platform_admin(email='STAFF@ergonosis.com') is True
        assert is_platform_admin(email='nope@ergonosis.com') is False
