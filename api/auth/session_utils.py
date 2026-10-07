"""Session helpers (fixation prevention, safe redirects)."""

from __future__ import annotations

import secrets
from urllib.parse import urlparse

from flask import current_app, session


def regenerate_session() -> None:
    """Issue a new server-side session id to prevent session fixation."""
    interface = current_app.session_interface
    old_sid = getattr(session, "sid", None)
    key_prefix = current_app.config.get("SESSION_KEY_PREFIX", "session:")

    session.clear()

    new_sid = secrets.token_urlsafe(32)
    if hasattr(session, "sid"):
        session.sid = new_sid
    session.modified = True

    # Best-effort delete of the previous Redis (or store) key
    if not old_sid:
        return
    try:
        redis_client = getattr(interface, "client", None) or getattr(
            interface, "redis", None
        )
        if redis_client is not None:
            redis_client.delete(f"{key_prefix}{old_sid}")
    except Exception:
        pass


def safe_post_login_url(candidate: str | None) -> str:
    """Return a portal URL only (blocks open redirects)."""
    portal = (current_app.config.get("PORTAL_URL") or "http://localhost:5175").rstrip(
        "/"
    )
    default_path = current_app.config.get("PORTAL_POST_LOGIN_PATH") or "/connections"
    default = f"{portal}{default_path}"

    if not candidate:
        return default

    candidate = candidate.strip()
    if candidate.startswith("/") and not candidate.startswith("//"):
        return f"{portal}{candidate}"

    parsed = urlparse(candidate)
    portal_parsed = urlparse(portal)
    if (
        parsed.scheme in {"http", "https"}
        and parsed.netloc == portal_parsed.netloc
        and (parsed.path or "/").startswith("/")
    ):
        return candidate

    return default
