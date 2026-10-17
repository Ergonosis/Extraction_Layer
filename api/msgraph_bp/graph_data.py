"""Load microsoft/ms_graph_email_client for portal delegated exports."""

from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path
from typing import Any


_CLIENT_PATH = (
    Path(__file__).resolve().parents[2]
    / "microsoft"
    / "ms_graph_email_client.py"
)


@lru_cache(maxsize=1)
def load_graph_client_class() -> type:
    """Import ``MicrosoftGraphEmailClient`` from the legacy microsoft module."""
    if not _CLIENT_PATH.is_file():
        raise RuntimeError(f"MS Graph client not found at {_CLIENT_PATH}")
    spec = importlib.util.spec_from_file_location(
        "portal_ms_graph_email_client", _CLIENT_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load MS Graph client module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cls = getattr(module, "MicrosoftGraphEmailClient", None)
    if cls is None:
        raise RuntimeError("MicrosoftGraphEmailClient is missing")
    return cls


def client_from_access_token(access_token: str) -> Any:
    """Build a Graph client that uses an in-memory delegated access token."""
    cls = load_graph_client_class()
    return cls.from_access_token(access_token)
