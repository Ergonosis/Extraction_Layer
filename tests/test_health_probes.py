"""Probe behavior without a live database, Redis, or GCP."""

from unittest.mock import MagicMock

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

from src.api.app import create_app
from src.api.config import Config
from src.api.session_store import PortalSessionInterface


@pytest.fixture
def probe_client(monkeypatch):
    class ProbeConfig(Config):
        FLASK_ENV = 'development'
        ENABLE_DEV_LOGIN = False
        SECRET_KEY = 'test-probe-signing-key'
        SESSION_BACKEND = 'sqlalchemy'
        RATELIMIT_STORAGE_BACKEND = 'sqlalchemy'
        RATELIMIT_ENABLED = True
        SQLALCHEMY_DATABASE_URI = 'postgresql+psycopg://test@localhost/test'

    app = create_app(ProbeConfig)
    for method in ('_retrieve_session_data', '_upsert_session', '_delete_session'):
        monkeypatch.setattr(
            PortalSessionInterface, method, MagicMock(side_effect=AssertionError('Probe touched session'))
        )
    client = app.test_client()
    # A valid existing cookie must not cause a session lookup or refresh on probes.
    client.set_cookie(app.config['SESSION_COOKIE_NAME'], app.session_interface._sign(app, 'existing-session'))
    return client


@pytest.mark.parametrize('method', ['GET', 'HEAD'])
def test_liveness_never_touches_database_session_or_rate_storage(probe_client, monkeypatch, method):
    connect = MagicMock(side_effect=AssertionError('Liveness accessed DB'))
    monkeypatch.setattr(Engine, 'connect', connect)
    for _ in range(40):
        response = probe_client.open('/api/health', method=method)
        assert response.status_code == 200
        assert 'Set-Cookie' not in response.headers
        assert response.headers['Cache-Control'] == 'no-store'
    connect.assert_not_called()


def test_readiness_only_checks_database_without_consuming_limits_or_refreshing_session(probe_client, monkeypatch):
    connect = MagicMock()
    connection = connect.return_value.__enter__.return_value
    monkeypatch.setattr(Engine, 'connect', connect)
    for _ in range(40):
        response = probe_client.get('/api/ready')
        assert response.status_code == 200
        assert response.json == {'status': 'ok'}
        assert 'Set-Cookie' not in response.headers
    assert connection.execute.call_count == 40
    assert all(str(call.args[0]) == 'SELECT 1' for call in connection.execute.call_args_list)


def test_database_failure_only_fails_readiness_and_does_not_expose_details(probe_client, monkeypatch):
    monkeypatch.setattr(
        Engine, 'connect', MagicMock(side_effect=OperationalError('private SQL details', {}, Exception()))
    )
    response = probe_client.get('/api/ready')
    assert response.status_code == 503
    assert response.json == {'status': 'unavailable'}
    assert 'Set-Cookie' not in response.headers
    assert probe_client.get('/api/health').status_code == 200
