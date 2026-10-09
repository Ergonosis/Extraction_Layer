import json
from datetime import date, timedelta

import pytest

from extractors.export_helpers import (
    build_export_filename,
    filter_accounts_and_transactions,
    resolve_date_range,
    resolve_export_prefix,
    strip_balances,
    write_export,
)


def test_resolve_date_range_explicit():
    start, end = resolve_date_range(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
    )
    assert start == date(2024, 1, 1)
    assert end == date(2024, 1, 31)


def test_resolve_date_range_hard_pull():
    start, end = resolve_date_range(
        end_date=date(2024, 6, 15),
        is_hard_pull=True,
    )
    assert start == date(2000, 1, 1)
    assert end == date(2024, 6, 15)


def test_resolve_date_range_window_days():
    end = date(2024, 6, 15)
    start, resolved_end = resolve_date_range(end_date=end, window_days=7)
    assert resolved_end == end
    assert start == end - timedelta(days=7)


def test_resolve_date_range_default_window_is_seven_days():
    end = date(2024, 6, 15)
    start, resolved_end = resolve_date_range(end_date=end)
    assert start == end - timedelta(days=7)
    assert resolved_end == end


def test_resolve_date_range_invalid_window():
    with pytest.raises(ValueError, match="window_days"):
        resolve_date_range(end_date=date(2024, 6, 15), window_days=0)
    with pytest.raises(ValueError, match="window_days"):
        resolve_date_range(end_date=date(2024, 6, 15), window_days=-1)


def test_resolve_date_range_start_after_end():
    with pytest.raises(ValueError, match="start_date"):
        resolve_date_range(
            start_date=date(2024, 6, 20),
            end_date=date(2024, 6, 15),
        )


def test_filter_no_filter_keeps_all():
    accounts = [
        {"account_id": "a1", "name": "Checking"},
        {"account_id": "a2", "name": "Saving"},
    ]
    txns = [
        {"account_id": "a1", "amount": 1},
        {"account_id": "a2", "amount": 2},
    ]
    fa, ft = filter_accounts_and_transactions(accounts, txns, None)
    assert fa == accounts
    assert ft == txns


def test_filter_by_name_drops_other_account_transactions():
    accounts = [
        {"account_id": "a1", "name": "Plaid Checking"},
        {"account_id": "a2", "name": "Plaid Saving"},
    ]
    txns = [
        {"account_id": "a1", "amount": 1},
        {"account_id": "a2", "amount": 2},
        {"account_id": "a1", "amount": 3},
    ]
    fa, ft = filter_accounts_and_transactions(accounts, txns, "Checking")
    assert [a["account_id"] for a in fa] == ["a1"]
    assert [t["amount"] for t in ft] == [1, 3]


def test_filter_empty_accounts():
    fa, ft = filter_accounts_and_transactions([], [{"account_id": "a1"}], "Checking")
    assert fa == []
    assert ft == []


def test_strip_balances():
    accounts = [
        {"account_id": "a1", "name": "Checking", "balances": {"current": 10}},
        {"account_id": "a2", "name": "Saving"},
    ]
    out = strip_balances(accounts)
    assert "balances" not in out[0]
    assert out[0]["name"] == "Checking"
    assert out[1] == {"account_id": "a2", "name": "Saving"}
    assert "balances" in accounts[0]


def test_resolve_export_prefix():
    assert resolve_export_prefix(is_hard_pull=True) == "full_history"
    assert resolve_export_prefix(window_days=7) == "weekly"
    assert resolve_export_prefix() == "range"
    assert resolve_export_prefix(prefix="custom") == "custom"


def test_build_export_filename_with_and_without_item_id(tmp_path):
    with_id = build_export_filename(
        str(tmp_path), "range", date(2024, 1, 1), date(2024, 1, 31), item_id="item-1"
    )
    assert with_id.endswith("range_2024-01-01_to_2024-01-31_item-1.json")
    without = build_export_filename(
        str(tmp_path), "range", date(2024, 1, 1), date(2024, 1, 31)
    )
    assert without.endswith("range_2024-01-01_to_2024-01-31.json")


def test_write_export_creates_dirs_and_roundtrips(tmp_path):
    path = tmp_path / "nested" / "out.json"
    data = {"accounts": [], "start": date(2024, 1, 1)}
    returned = write_export(data, str(path))
    assert returned == str(path)
    assert path.exists()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["accounts"] == []
    assert loaded["start"] == "2024-01-01"
