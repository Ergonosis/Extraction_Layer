"""Job shutdown checks with no database or network calls."""

from unittest.mock import MagicMock

import pytest

from src.api import migrate


@pytest.mark.parametrize('code', [0, 1])
def test_migration_always_shuts_down_proxy_and_preserves_exit_code(monkeypatch, code):
    run = MagicMock(return_value=MagicMock(returncode=code))
    shutdown = MagicMock()
    monkeypatch.setattr(migrate.subprocess, 'run', run)
    monkeypatch.setattr(migrate, 'urlopen', shutdown)
    assert migrate.main() == code
    run.assert_called_once_with(['flask', 'db', 'upgrade'], check=False)
    request = shutdown.call_args.args[0]
    assert request.full_url == 'http://127.0.0.1:9091/quitquitquit'
    assert request.get_method() == 'POST'


def test_process_error_still_requests_proxy_shutdown(monkeypatch):
    monkeypatch.setattr(migrate.subprocess, 'run', MagicMock(side_effect=OSError('No command')))
    shutdown = MagicMock()
    monkeypatch.setattr(migrate, 'urlopen', shutdown)
    with pytest.raises(OSError, match='No command'):
        migrate.main()
    shutdown.assert_called_once()
