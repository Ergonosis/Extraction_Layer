import os
import sys
from pathlib import Path

import pytest

# plaid/ on path so imports work from repo root or plaid/
_PLAID_DIR = Path(__file__).resolve().parents[1]
if str(_PLAID_DIR) not in sys.path:
    sys.path.insert(0, str(_PLAID_DIR))

# Fake creds so apps can import without a real .env (JSON persistence tests)
os.environ.setdefault("PLAID_CLIENT_ID", "test-client-id")
os.environ.setdefault("PLAID_SECRET", "test-secret")
os.environ.setdefault("PLAID_ENV", "sandbox")


@pytest.fixture
def records_dir(tmp_path, monkeypatch):
    """Isolate persistence under a fresh temp directory."""
    monkeypatch.setenv("RECORDS_DIR", str(tmp_path))
    return tmp_path
