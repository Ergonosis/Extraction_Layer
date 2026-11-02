"""PostgreSQL storage backend for flask-limiter / limits (fixed-window).

Registered as URI scheme ``portal-postgres://``. Uses atomic upserts so
multiple Cloud Run instances share the same counters.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from limits.storage.base import Storage
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


class PortalPostgresStorage(Storage):
    """Shared fixed-window counters in PostgreSQL."""

    STORAGE_SCHEME = ["portal-postgres"]

    def __init__(
        self,
        uri: str | None = None,
        wrap_exceptions: bool = False,
        **options: object,
    ) -> None:
        super().__init__(uri, wrap_exceptions=wrap_exceptions)
        database_url = str(options.get("database_url") or "").strip()
        if not database_url:
            raise ValueError(
                "portal-postgres storage requires storage_options.database_url"
            )
        self._engine: Engine = create_engine(
            database_url,
            pool_pre_ping=True,
            pool_size=int(options.get("pool_size") or 2),
            max_overflow=int(options.get("max_overflow") or 1),
        )

    @property
    def base_exceptions(self) -> type[Exception] | tuple[type[Exception], ...]:
        from sqlalchemy.exc import SQLAlchemyError

        return SQLAlchemyError

    def check(self) -> bool:
        with self._engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True

    def reset(self) -> None:
        with self._engine.begin() as conn:
            conn.execute(text("DELETE FROM rate_limit_buckets"))

    def clear(self, key: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text("DELETE FROM rate_limit_buckets WHERE key = :key"),
                {"key": key},
            )

    def get(self, key: str) -> int:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT count, expires_at FROM rate_limit_buckets WHERE key = :key"
                ),
                {"key": key},
            ).one_or_none()
            if row is None:
                return 0
            count, expires_at = row
            now = datetime.now(timezone.utc)
            if expires_at is not None and getattr(expires_at, "tzinfo", None) is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at is None or expires_at <= now:
                return 0
            return int(count or 0)

    def get_expiry(self, key: str) -> int:
        with self._engine.connect() as conn:
            row = conn.execute(
                text("SELECT expires_at FROM rate_limit_buckets WHERE key = :key"),
                {"key": key},
            ).one_or_none()
            if row is None or row[0] is None:
                return int(time.time())
            expires_at = row[0]
            if getattr(expires_at, "tzinfo", None) is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            if expires_at <= now:
                return int(time.time())
            return int(expires_at.timestamp())

    def incr(self, key: str, expiry: int, amount: int = 1) -> int:
        # Fixed-window: first hit sets expiry; subsequent hits until expiry bump count.
        sql = text(
            """
            INSERT INTO rate_limit_buckets (key, count, expires_at)
            VALUES (
                :key,
                :amount,
                timezone('utc', now()) + make_interval(secs => :expiry)
            )
            ON CONFLICT (key) DO UPDATE SET
                count = CASE
                    WHEN rate_limit_buckets.expires_at <= timezone('utc', now())
                    THEN EXCLUDED.count
                    ELSE rate_limit_buckets.count + EXCLUDED.count
                END,
                expires_at = CASE
                    WHEN rate_limit_buckets.expires_at <= timezone('utc', now())
                    THEN EXCLUDED.expires_at
                    ELSE rate_limit_buckets.expires_at
                END
            RETURNING count
            """
        )
        with self._engine.begin() as conn:
            count = conn.execute(
                sql,
                {"key": key, "amount": int(amount), "expiry": int(expiry)},
            ).scalar_one()
            return int(count)
