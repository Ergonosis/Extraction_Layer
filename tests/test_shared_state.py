"""Shared-state wiring and failures with mocks only; no DB, Redis, or GCP."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from src.api import rate_limit
from src.api.app import create_app
from src.api.auth import session_utils
from src.api.config import Config
from src.api.extensions import db
from src.api.models import PortalSession
from src.api.rate_limit_storage import PortalPostgresStorage
from src.api.session_store import PortalSessionInterface, init_sessions


def test_app_factory_registers_shared_sessions_without_connecting_or_creating_tables(monkeypatch):
    monkeypatch.setattr(Engine, 'connect', MagicMock(side_effect=AssertionError('No DB access allowed')))
    monkeypatch.setattr(PortalSession.__table__, 'create', MagicMock(side_effect=AssertionError('No startup DDL')))

    class TestConfig(Config):
        FLASK_ENV = 'development'
        ENABLE_DEV_LOGIN = False
        SECRET_KEY = 'test-only-secret'
        SESSION_BACKEND = 'sqlalchemy'
        RATELIMIT_STORAGE_BACKEND = 'sqlalchemy'
        DATABASE_URL = 'postgresql+psycopg://test@localhost/test'
        SQLALCHEMY_DATABASE_URI = DATABASE_URL

    first, second = create_app(TestConfig), create_app(TestConfig)
    assert isinstance(first.session_interface, PortalSessionInterface)
    assert first.session_interface.sql_session_model is second.session_interface.sql_session_model is PortalSession
    with first.app_context():
        assert first.config['RATELIMIT_STORAGE_OPTIONS']['engine'] is db.engine
    with second.app_context():
        assert rate_limit.limiter._storage._engine is db.engine
    Engine.connect.assert_not_called()
    PortalSession.__table__.create.assert_not_called()


@pytest.mark.parametrize('backend,url', [('memory', ''), ('unknown', ''), ('redis', '')])
def test_session_backend_rejects_unsupported_or_missing_configuration(backend, url):
    app = Flask(__name__)
    app.config.update(SESSION_BACKEND=backend, REDIS_URL=url)
    with pytest.raises(RuntimeError):
        init_sessions(app)


@pytest.mark.parametrize('backend,url', [('memory', ''), ('unknown', ''), ('redis', '')])
def test_limiter_rejects_unsupported_or_missing_configuration(backend, url, monkeypatch):
    app = Flask(__name__)
    app.config.update(RATELIMIT_STORAGE_BACKEND=backend, REDIS_URL=url)
    initialize = MagicMock()
    monkeypatch.setattr(rate_limit.limiter, 'init_app', initialize)
    with pytest.raises(RuntimeError):
        rate_limit.init_limiter(app)
    initialize.assert_not_called()


def test_explicit_redis_limiter_does_not_use_postgres_or_memory(monkeypatch):
    app = Flask(__name__)
    app.config.update(
        RATELIMIT_STORAGE_BACKEND='redis', REDIS_URL='redis://test/0', RATELIMIT_STORAGE_OPTIONS={'old': 1}
    )
    monkeypatch.setattr(rate_limit.limiter, 'init_app', MagicMock())
    rate_limit.init_limiter(app)
    assert app.config['RATELIMIT_STORAGE_URI'] == 'redis://test/0'
    assert 'RATELIMIT_STORAGE_OPTIONS' not in app.config


def test_sqlite_is_not_accepted_as_shared_postgres_limiter():
    app = Flask(__name__)
    app.config.update(RATELIMIT_STORAGE_BACKEND='sqlalchemy', SQLALCHEMY_DATABASE_URI='sqlite://')
    with pytest.raises(RuntimeError, match='PostgreSQL is required'):
        rate_limit.init_limiter(app)


def test_revocation_uses_the_backend_store_key_and_propagates_failure():
    app = Flask(__name__)
    interface = MagicMock()
    interface._get_store_id.return_value = 'portal:session:old'
    app.session_interface = interface
    with app.app_context():
        session_utils._delete_store_key(None)
        interface._delete_session.assert_not_called()
        session_utils._delete_store_key('old')
        interface._delete_session.assert_called_once_with('portal:session:old')
        interface._delete_session.side_effect = RuntimeError('Storage unavailable')
        with pytest.raises(RuntimeError, match='Storage unavailable'):
            session_utils._delete_store_key('old')


def test_login_rotation_and_logout_revoke_previous_sid(monkeypatch):
    class Session(dict):
        sid = 'old'
        modified = False

    value = Session(user_id=1, organization_id=2)
    revoke = MagicMock()
    monkeypatch.setattr(session_utils, 'session', value)
    monkeypatch.setattr(session_utils, '_delete_store_key', revoke)
    session_utils.regenerate_session()
    revoke.assert_called_once_with('old')
    assert value.sid != 'old' and value.modified and not value
    sid = value.sid
    value['user_id'] = 1
    session_utils.destroy_session()
    assert revoke.call_args.args == (sid,)
    assert value.sid != sid and not value


@pytest.fixture
def storage():
    engine = MagicMock(spec=Engine)
    return PortalPostgresStorage('portal-postgres://', engine=engine), engine


def test_postgres_storage_requires_the_shared_engine():
    with pytest.raises(TypeError, match='application SQLAlchemy engine'):
        PortalPostgresStorage('portal-postgres://', database_url='postgresql://test')


def test_counter_uses_atomic_upsert_and_database_time(storage):
    counter, engine = storage
    connection = engine.begin.return_value.__enter__.return_value
    connection.execute.return_value.scalar_one.return_value = 3
    assert counter.incr('endpoint:key', 60, amount=2) == 3
    statement, parameters = connection.execute.call_args.args
    assert parameters == {'key': 'endpoint:key', 'amount': 2, 'expiry': 60}
    assert 'ON CONFLICT' in str(statement) and 'CURRENT_TIMESTAMP' in str(statement)
    assert "timezone('utc'" not in str(statement)
    assert 'ELSE rate_limit_buckets.expires_at' in str(statement)


def test_counter_reads_expiry_using_database_time(storage):
    counter, engine = storage
    connection = engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.scalar_one_or_none.return_value = None
    assert counter.get('expired') == 0
    statement, parameters = connection.execute.call_args.args
    assert 'expires_at > CURRENT_TIMESTAMP' in str(statement)
    assert parameters == {'key': 'expired'}
    connection.execute.return_value.scalar_one.return_value = 1234.5
    assert counter.get_expiry('expired') == 1234
    assert 'CURRENT_TIMESTAMP' in str(connection.execute.call_args.args[0])


def test_storage_failure_is_not_replaced_with_an_in_memory_counter(storage):
    counter, engine = storage
    engine.begin.side_effect = SQLAlchemyError('Unavailable')
    with pytest.raises(SQLAlchemyError):
        counter.incr('key', 60)


def test_sqlalchemy_session_deletion_rolls_back_and_propagates_failure(monkeypatch):
    interface = PortalSessionInterface(Flask(__name__))
    client = SimpleNamespace(session=MagicMock())
    interface.sql_session_model = SimpleNamespace(query=MagicMock())
    interface.sql_session_model.query.filter_by.return_value.delete.side_effect = RuntimeError('Unavailable')
    interface.client = client
    # Call the persistence function once without retry sleeps.
    with pytest.raises(RuntimeError, match='Unavailable'):
        type(interface)._delete_session.__wrapped__(interface, 'portal:session:old')
    client.session.rollback.assert_called_once()
    client.session.commit.assert_not_called()
