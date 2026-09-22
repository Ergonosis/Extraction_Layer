import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# plaid/ on path so `import apps` works when pytest is run from repo root or plaid/
_PLAID_DIR = Path(__file__).resolve().parents[1]
if str(_PLAID_DIR) not in sys.path:
    sys.path.insert(0, str(_PLAID_DIR))

# Fake creds + stub Plaid extractor so apps imports without plaid-python / real .env
os.environ.setdefault("PLAID_CLIENT_ID", "test-client-id")
os.environ.setdefault("PLAID_SECRET", "test-secret")
os.environ.setdefault("PLAID_ENV", "sandbox")

_mock_ext = MagicMock()
_mock_ext.PlaidExtractor.return_value.client = MagicMock()
sys.modules["extractors.plaid_ext"] = _mock_ext


@pytest.fixture
def records_dir(tmp_path, monkeypatch):
    """Isolate persistence under a fresh temp directory."""
    monkeypatch.setenv("RECORDS_DIR", str(tmp_path))
    return tmp_path
