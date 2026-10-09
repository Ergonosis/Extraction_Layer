"""Functional tests: fetch_and_store with a mocked Plaid client (no network)."""

import json
from datetime import date
from unittest.mock import MagicMock

from extractors.plaid_ext import fetch_and_store


def _page(*, accounts, transactions, total_transactions, item=None, request_id="req-1"):
    return {
        "accounts": accounts,
        "item": item or {"item_id": "item-1"},
        "request_id": request_id,
        "transactions": transactions,
        "total_transactions": total_transactions,
    }


def test_fetch_and_store_writes_filtered_export(tmp_path):
    client = MagicMock()
    client.transactions_get.return_value.to_dict.return_value = _page(
        accounts=[
            {"account_id": "a1", "name": "Plaid Checking"},
            {"account_id": "a2", "name": "Plaid Saving"},
        ],
        transactions=[
            {"account_id": "a1", "amount": 10},
            {"account_id": "a2", "amount": 20},
        ],
        total_transactions=2,
    )

    path = fetch_and_store(
        client,
        access_token="access-test",
        item_id="item-1",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        account_filter="Checking",
        output_dir=str(tmp_path),
    )

    data = json.loads(open(path, encoding="utf-8").read())
    assert [a["account_id"] for a in data["accounts"]] == ["a1"]
    assert [t["amount"] for t in data["transactions"]] == [10]
    assert data["filters"]["account_filter"] == "Checking"
    assert data["filters"]["item_id"] == "item-1"
    assert client.transactions_get.called
    assert path.endswith("range_2024-01-01_to_2024-01-31_item-1.json")


def test_fetch_and_store_multi_page_combines_transactions(tmp_path):
    page1 = _page(
        accounts=[{"account_id": "a1", "name": "Checking"}],
        transactions=[{"account_id": "a1", "amount": 1}],
        total_transactions=2,
        request_id="req-page-1",
    )
    page2 = _page(
        accounts=[{"account_id": "should-ignore"}],
        transactions=[{"account_id": "a1", "amount": 2}],
        total_transactions=2,
        request_id="should-ignore",
    )

    client = MagicMock()
    client.transactions_get.return_value.to_dict.side_effect = [page1, page2]

    path = fetch_and_store(
        client,
        access_token="access-test",
        item_id="item-1",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        output_dir=str(tmp_path),
    )

    data = json.loads(open(path, encoding="utf-8").read())
    assert [t["amount"] for t in data["transactions"]] == [1, 2]
    assert data["accounts"] == [{"account_id": "a1", "name": "Checking"}]
    assert data["item"]["item_id"] == "item-1"
    assert data["request_id"] == "req-page-1"
    assert client.transactions_get.call_count == 2
