"""PostgreSQL storage backend for flask-limiter / limits (fixed-window).

Registered as URI scheme ``portal-postgres://``. Uses atomic upserts so
multiple Cloud Run instances share the same counters.
"""

from __future__ import annotations

from typing import ClassVar

from limits.storage.base import Storage
from sqlalchemy import text
from sqlalchemy.engine import Engine


class PortalPostgresStorage(Storage):
    """Shared fixed-window counters in PostgreSQL."""

    STORAGE_SCHEME: ClassVar[list[str]] = ['portal-postgres']

    def __init__(self, uri: str | None = None, wrap_exceptions: bool = False, **options: object) -> None:
        super().__init__(uri, wrap_exceptions=wrap_exceptions)
        engine = options.get('engine')
        if not isinstance(engine, Engine):
            raise TypeError('portal-postgres storage requires the application SQLAlchemy engine')
        self._engine = engine

    @property
    def base_exceptions(self) -> type[Exception] | tuple[type[Exception], ...]:
        from sqlalchemy.exc import SQLAlchemyError

        return SQLAlchemyError

    def check(self) -> bool:
        with self._engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        return True

    def reset(self) -> None:
        with self._engine.begin() as conn:
            conn.execute(text('DELETE FROM rate_limit_buckets'))

    def clear(self, key: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(text('DELETE FROM rate_limit_buckets WHERE key = :key'), {'key': key})

    def get(self, key: str) -> int:
        with self._engine.connect() as conn:
            count = conn.execute(
                text('SELECT count FROM rate_limit_buckets WHERE key = :key AND expires_at > CURRENT_TIMESTAMP'),
                {'key': key},
            ).scalar_one_or_none()
            return int(count or 0)

    def get_expiry(self, key: str) -> int:
        with self._engine.connect() as conn:
            expiry = conn.execute(
                text(
                    'SELECT EXTRACT(EPOCH FROM COALESCE('
                    '(SELECT expires_at FROM rate_limit_buckets '
                    'WHERE key = :key AND expires_at > CURRENT_TIMESTAMP), CURRENT_TIMESTAMP))'
                ),
                {'key': key},
            ).scalar_one()
            return int(expiry)

    def incr(self, key: str, expiry: int, amount: int = 1) -> int:
        # Fixed-window: first hit sets expiry; subsequent hits until expiry bump count.
        sql = text(
            """
            INSERT INTO rate_limit_buckets (key, count, expires_at)
            VALUES (
                :key,
                :amount,
                CURRENT_TIMESTAMP + make_interval(secs => :expiry)
            )
            ON CONFLICT (key) DO UPDATE SET
                count = CASE
                    WHEN rate_limit_buckets.expires_at <= CURRENT_TIMESTAMP
                    THEN EXCLUDED.count
                    ELSE rate_limit_buckets.count + EXCLUDED.count
                END,
                expires_at = CASE
                    WHEN rate_limit_buckets.expires_at <= CURRENT_TIMESTAMP
                    THEN EXCLUDED.expires_at
                    ELSE rate_limit_buckets.expires_at
                END
            RETURNING count
            """
        )
        with self._engine.begin() as conn:
            count = conn.execute(sql, {'key': key, 'amount': int(amount), 'expiry': int(expiry)}).scalar_one()
            return int(count)
