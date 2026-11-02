"""Use Flask-Session persistence without its implicit table creation at startup."""

from flask import Flask, Request
from flask.sessions import NullSession
from flask_session import Session
from flask_session.base import ServerSideSessionInterface
from flask_session.defaults import Defaults
from flask_session.sqlalchemy import SqlAlchemySessionInterface

from src.api.extensions import db
from src.api.models import PortalSession


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
            serialization_format=app.config.get('SESSION_SERIALIZATION_FORMAT', Defaults.SESSION_SERIALIZATION_FORMAT),
            cleanup_n_requests=app.config.get('SESSION_CLEANUP_N_REQUESTS', Defaults.SESSION_CLEANUP_N_REQUESTS),
        )


def init_sessions(app: Flask) -> None:
    backend = (app.config.get('SESSION_BACKEND') or 'sqlalchemy').strip().lower()
    if backend == 'sqlalchemy':
        app.session_interface = PortalSessionInterface(app)
    elif backend == 'redis':
        redis_url = (app.config.get('REDIS_URL') or '').strip()
        if not redis_url:
            raise RuntimeError('REDIS_URL must be set when SESSION_BACKEND=redis')
        import redis

        app.config['SESSION_TYPE'] = 'redis'
        app.config['SESSION_REDIS'] = redis.from_url(redis_url)
        Session(app)
    else:
        raise RuntimeError(f'Unsupported SESSION_BACKEND={backend!r}; use sqlalchemy or redis')
