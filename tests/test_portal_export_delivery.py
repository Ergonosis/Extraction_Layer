"""Verify export delivery with fake credentials and filesystem fixtures only."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.api.plaid_bp import service


@pytest.fixture
def export_dependencies(monkeypatch):
    integration = SimpleNamespace(
        status='connected', plaid_credential=SimpleNamespace(access_token_enc=b'ciphertext', item_id='item-test')
    )
    monkeypatch.setattr(service, '_plaid_integration', lambda **_: integration)
    monkeypatch.setattr(service, 'get_plaid_client', lambda: 'mock-client')
    monkeypatch.setattr(service, 'decrypt_token', lambda _: 'test-token')
    monkeypatch.setattr(service, 'serialize_integration', lambda _: {'status': 'connected'})
    monkeypatch.setattr(service, 'audit', MagicMock())
    return integration


def test_export_returns_payload_and_removes_temporary_files(export_dependencies, monkeypatch):
    paths = []
    payload = {'transactions': [{'id': 't1', 'amount': 10}], 'accounts': []}

    def fetch(client, token, **kwargs):
        assert client == 'mock-client' and token == 'test-token'
        assert kwargs['window_days'] == 7 and kwargs['account_filter'] == ['checking']
        path = Path(kwargs['output_dir']) / 'export.json'
        path.write_text(json.dumps(payload))
        paths.append(path)
        return str(path)

    monkeypatch.setattr(service, 'fetch_and_store', fetch)
    result = service.run_export(user_id=1, organization_id=2, window_days=7, account_filter=['checking'])
    assert result == {
        'filename': 'export.json',
        'item_id': 'item-test',
        'export': payload,
        'integration': {'status': 'connected'},
    }
    assert 'file' not in result and 'test-token' not in json.dumps(result)
    assert not paths[0].exists() and not paths[0].parent.exists()


def test_export_failure_still_cleans_temporary_directory(export_dependencies, monkeypatch):
    paths = []

    def fetch(*_, **kwargs):
        paths.append(Path(kwargs['output_dir']))
        raise OSError('mock disk failure')

    monkeypatch.setattr(service, 'fetch_and_store', fetch)
    with pytest.raises(service.PlaidServiceError) as error:
        service.run_export(user_id=1, organization_id=2)
    assert error.value.status_code == 502
    assert not paths[0].exists()


def test_disconnected_export_is_rejected_before_fetch(export_dependencies, monkeypatch):
    export_dependencies.status = 'not_connected'
    fetch = MagicMock()
    monkeypatch.setattr(service, 'fetch_and_store', fetch)
    with pytest.raises(service.PlaidServiceError) as error:
        service.run_export(user_id=1, organization_id=2)
    assert error.value.status_code == 400
    fetch.assert_not_called()
