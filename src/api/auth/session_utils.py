"""Session helpers (fixation prevention, safe redirects, logout destroy)."""

from __future__ import annotations

import secrets
from urllib.parse import urlparse

from flask import current_app, session


def _delete_store_key(sid: str | None) -> None:
    """Revoke a stored session; backend failure must not look like successful logout."""
    if sid:
        interface = current_app.session_interface
        interface._delete_session(interface._get_store_id(sid))


def regenerate_session() -> None:
    """Issue a new server-side session id to prevent session fixation."""
    old_sid = getattr(session, 'sid', None)

    session.clear()

    new_sid = secrets.token_urlsafe(32)
    if hasattr(session, 'sid'):
        session.sid = new_sid
    session.modified = True

    _delete_store_key(old_sid)


def destroy_session() -> None:
    """Fully destroy the current server-side session (logout)."""
    old_sid = getattr(session, 'sid', None)
    session.clear()
    session.modified = True
    _delete_store_key(old_sid)
    # Force a new empty sid so the old cookie cannot reopen the deleted record.
    new_sid = secrets.token_urlsafe(32)
    if hasattr(session, 'sid'):
        session.sid = new_sid


def safe_post_login_url(candidate: str | None) -> str:
    """Return a portal URL only (blocks open redirects)."""
    portal = (current_app.config.get('PORTAL_URL') or 'http://localhost:5175').rstrip('/')
    default_path = current_app.config.get('PORTAL_POST_LOGIN_PATH') or '/connections'
    default = f'{portal}{default_path}'

    if not candidate:
        return default

    candidate = candidate.strip()
    if candidate.startswith('/') and not candidate.startswith('//'):
        return f'{portal}{candidate}'

    parsed = urlparse(candidate)
    portal_parsed = urlparse(portal)
    if (
        parsed.scheme in {'http', 'https'}
        and parsed.netloc == portal_parsed.netloc
        and (parsed.path or '/').startswith('/')
    ):
        return candidate

    return default
