"""Deterministic logout race: stale upsert must not resurrect a revoked SID."""

from __future__ import annotations

import threading
from datetime import timedelta
from types import SimpleNamespace

import pytest
from flask import Flask

from src.api.extensions import db
from src.api.models import PortalSession, SessionRevocation
from src.api.session_store import PortalSessionInterface


@pytest.fixture
def revocation_app():
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY='test-revocation-secret',
        SQLALCHEMY_DATABASE_URI='sqlite://',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_KEY_PREFIX='portal:session:',
        SESSION_PERMANENT=True,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=1),
    )
    db.init_app(app)
    with app.app_context():
        db.create_all()
        interface = PortalSessionInterface(app)
        app.session_interface = interface
        yield SimpleNamespace(app=app, interface=interface, db=db)
        db.session.remove()
        db.drop_all()


def _raw_upsert():
    method = PortalSessionInterface.__dict__['_upsert_session']
    return getattr(method, '__wrapped__', method)


def _seed_session(interface: PortalSessionInterface, sid: str, payload: dict) -> str:
    store_id = interface._get_store_id(sid)
    session = interface.session_class(sid=sid)
    session.update(payload)
    _raw_upsert()(interface, timedelta(hours=1), session, store_id)
    return store_id


def test_stale_upsert_cannot_resurrect_revoked_session(revocation_app):
    """Request A pauses before save; B revokes; A finishes — old SID stays dead."""
    app = revocation_app.app
    interface = revocation_app.interface
    sid = 'authenticated-sid'

    with app.app_context():
        store_id = _seed_session(interface, sid, {'user_id': 7, 'organization_id': 3})
        assert interface._retrieve_session_data(store_id)['user_id'] == 7

    at_barrier = threading.Event()
    release_barrier = threading.Event()
    upsert_errors: list[BaseException] = []
    real_upsert = _raw_upsert()

    def blocked_upsert(session_lifetime, session, upsert_store_id):
        at_barrier.set()
        if not release_barrier.wait(timeout=5):
            raise TimeoutError('Release barrier was not signaled')
        return real_upsert(interface, session_lifetime, session, upsert_store_id)

    interface._upsert_session = blocked_upsert

    stale = interface.session_class(sid=sid)
    stale.update({'user_id': 7, 'organization_id': 3, 'stale': True})

    def run_stale_save():
        try:
            with app.app_context():
                interface._upsert_session(timedelta(hours=1), stale, store_id)
        except BaseException as exc:  # noqa: BLE001 — capture for main thread
            upsert_errors.append(exc)

    worker = threading.Thread(target=run_stale_save)
    worker.start()
    assert at_barrier.wait(timeout=5), 'Stale request never reached upsert barrier'

    with app.app_context():
        interface._revoke_session(store_id)
        assert SessionRevocation.query.filter_by(store_id=store_id).one_or_none() is not None
        assert PortalSession.query.filter_by(session_id=store_id).one_or_none() is None
        assert interface._retrieve_session_data(store_id) is None

    release_barrier.set()
    worker.join(timeout=5)
    assert not worker.is_alive(), 'Stale upsert thread did not finish'
    assert upsert_errors == []

    with app.app_context():
        assert PortalSession.query.filter_by(session_id=store_id).one_or_none() is None
        assert interface._retrieve_session_data(store_id) is None


def test_revoke_blocks_direct_upsert_without_barrier(revocation_app):
    app = revocation_app.app
    interface = revocation_app.interface
    with app.app_context():
        store_id = _seed_session(interface, 'sid-b', {'user_id': 1})
        interface._revoke_session(store_id)
        revived = interface.session_class(sid='sid-b')
        revived['user_id'] = 1
        _raw_upsert()(interface, timedelta(hours=1), revived, store_id)
        assert interface._retrieve_session_data(store_id) is None
        assert PortalSession.query.filter_by(session_id=store_id).one_or_none() is None
