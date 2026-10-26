import os

import pytest

# Fake creds so apps can import without a real .env (JSON persistence tests)
os.environ.setdefault('PLAID_CLIENT_ID', 'test-client-id')
os.environ.setdefault('PLAID_SECRET', 'test-secret')
os.environ.setdefault('PLAID_ENV', 'sandbox')


@pytest.fixture
def records_dir(tmp_path, monkeypatch):
    """Isolate persistence under a fresh temp directory."""
    monkeypatch.setenv('RECORDS_DIR', str(tmp_path))
    return tmp_path
