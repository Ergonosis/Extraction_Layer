"""Use Flask-Session persistence without its implicit table creation at startup."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from flask import Flask, Request
from flask.sessions import NullSession
from flask_session import Session
from flask_session._utils import retry_query
from flask_session.base import ServerSideSession, ServerSideSessionInterface
from flask_session.defaults import Defaults
from flask_session.sqlalchemy import SqlAlchemySessionInterface
from itsdangerous import want_bytes

from src.api.extensions import db
from src.api.models import PortalSession, SessionRevocation


class PortalSessionInterface(SqlAlchemySessionInterface):
    def open_session(self, app: Flask, request: Request):
        if request.method in {'GET', 'HEAD'} and request.path in {'/api/health', '/api/ready'}:
            return NullSession()
        return super().open_session(app, request)

    def __init__(self, app: Flask):
        self.app = app
        self.client = db
        self.sql_session_model = PortalSession
        # Parent initialization dynamically defines a model and creates its table.
        # Keep its persistence methods, but leave DDL to the migration Job.
        ServerSideSessionInterface.__init__(
            self,
            app,
            key_prefix=app.config.get('SESSION_KEY_PREFIX', Defaults.SESSION_KEY_PREFIX),
            use_signer=app.config.get('SESSION_USE_SIGNER', Defaults.SESSION_USE_SIGNER),
            permanent=app.config.get('SESSION_PERMANENT', Defaults.SESSION_PERMANENT),
            sid_length=app.config.get('SESSION_ID_LENGTH', Defaults.SESSION_ID_LENGTH),
            serialization_format=app.config.get(
                'SESSION_SERIALIZATION_FORMAT', Defaults.SESSION_SERIALIZATION_FORMAT
            ),
            cleanup_n_requests=app.config.get(
                'SESSION_CLEANUP_N_REQUESTS', Defaults.SESSION_CLEANUP_N_REQUESTS
            ),
        )

    def _revocation_active(self, store_id: str) -> bool:
        row = SessionRevocation.query.filter_by(store_id=store_id).first()
        if row is None:
            return False
        if row.expires_at is not None and row.expires_at <= datetime.utcnow():
            return False
        return True

    @retry_query()
    def _revoke_session(self, store_id: str, ttl: timedelta | None = None) -> None:
        """Delete the live row and record a tombstone so later upserts cannot revive it."""
        lifetime = ttl if ttl is not None else self.app.permanent_session_lifetime
        now = datetime.utcnow()
        expires_at = now + lifetime
        try:
            self.sql_session_model.query.filter_by(session_id=store_id).delete(
                synchronize_session=False
            )
            row = SessionRevocation.query.filter_by(store_id=store_id).first()
            if row is None:
                self.client.session.add(
                    SessionRevocation(store_id=store_id, revoked_at=now, expires_at=expires_at)
                )
            else:
                row.revoked_at = now
                row.expires_at = expires_at
            self.client.session.commit()
        except Exception:
            self.client.session.rollback()
            raise

    @retry_query()
    def _retrieve_session_data(self, store_id: str) -> Optional[dict]:
        if self._revocation_active(store_id):
            return None

        record = self.sql_session_model.query.filter_by(session_id=store_id).first()
        if record and (record.expiry is None or record.expiry <= datetime.utcnow()):
            try:
                self.client.session.delete(record)
                self.client.session.commit()
            except Exception:
                self.client.session.rollback()
                raise
            record = None

        if record:
            serialized_session_data = want_bytes(record.data)
            return self.serializer.decode(serialized_session_data)
        return None

    @retry_query()
    def _upsert_session(
        self, session_lifetime: timedelta, session: ServerSideSession, store_id: str
    ) -> None:
        if self._revocation_active(store_id):
            return

        storage_expiration_datetime = datetime.utcnow() + session_lifetime
        serialized_session_data = self.serializer.encode(session)
        try:
            record = self.sql_session_model.query.filter_by(session_id=store_id).first()
            if record:
                record.data = serialized_session_data
                record.expiry = storage_expiration_datetime
            else:
                record = self.sql_session_model(
                    session_id=store_id,
                    data=serialized_session_data,
                    expiry=storage_expiration_datetime,
                )
                self.client.session.add(record)
            self.client.session.commit()
        except Exception:
            self.client.session.rollback()
            raise


def _install_redis_revocation(app: Flask, redis_client) -> None:
    """Prevent stale Redis upserts from recreating a revoked SID."""
    interface = app.session_interface
    revoke_prefix = 'portal:revoked:'
    original_upsert = interface._upsert_session
    original_retrieve = interface._retrieve_session_data
    original_delete = interface._delete_session

    def _revoked(store_id: str) -> bool:
        return bool(redis_client.exists(f'{revoke_prefix}{store_id}'))

    def _revoke_session(store_id: str, ttl: timedelta | None = None) -> None:
        lifetime = ttl if ttl is not None else app.permanent_session_lifetime
        original_delete(store_id)
        seconds = max(int(lifetime.total_seconds()), 1)
        redis_client.setex(f'{revoke_prefix}{store_id}', seconds, '1')

    def _upsert_session(session_lifetime, session, store_id):
        if _revoked(store_id):
            return None
        return original_upsert(session_lifetime, session, store_id)

    def _retrieve_session_data(store_id):
        if _revoked(store_id):
            return None
        return original_retrieve(store_id)

    interface._revoke_session = _revoke_session
    interface._upsert_session = _upsert_session
    interface._retrieve_session_data = _retrieve_session_data


def init_sessions(app: Flask) -> None:
    backend = (app.config.get('SESSION_BACKEND') or 'sqlalchemy').strip().lower()
    if backend == 'sqlalchemy':
        app.session_interface = PortalSessionInterface(app)
    elif backend == 'redis':
        redis_url = (app.config.get('REDIS_URL') or '').strip()
        if not redis_url:
            raise RuntimeError('REDIS_URL must be set when SESSION_BACKEND=redis')
        import redis

        client = redis.from_url(redis_url)
        app.config['SESSION_TYPE'] = 'redis'
        app.config['SESSION_REDIS'] = client
        Session(app)
        _install_redis_revocation(app, client)
    else:
        raise RuntimeError(f'Unsupported SESSION_BACKEND={backend!r}; use sqlalchemy or redis')
