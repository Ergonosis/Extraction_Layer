from extractors.plaid_pagination import fetch_all_transaction_pages


def test_single_page_captures_metadata_and_transactions():
    def fetch_page(offset, count):
        assert offset == 0
        return {
            "accounts": [{"account_id": "a1"}],
            "item": {"item_id": "item-1"},
            "request_id": "req-1",
            "transactions": [{"transaction_id": "t1"}],
            "total_transactions": 1,
        }

    result = fetch_all_transaction_pages(fetch_page, page_size=500)
    assert result["accounts"] == [{"account_id": "a1"}]
    assert result["item"] == {"item_id": "item-1"}
    assert result["request_id"] == "req-1"
    assert result["transactions"] == [{"transaction_id": "t1"}]
    assert result["total_transactions"] == 1


def test_multi_page_keeps_first_page_metadata_only():
    calls = []

    def fetch_page(offset, count):
        calls.append(offset)
        if offset == 0:
            return {
                "accounts": [{"account_id": "a1"}],
                "item": {"item_id": "item-1"},
                "request_id": "req-1",
                "transactions": [{"transaction_id": "t1"}],
                "total_transactions": 3,
            }
        if offset == 1:
            return {
                "accounts": [{"account_id": "should-ignore"}],
                "item": {"item_id": "should-ignore"},
                "request_id": "should-ignore",
                "transactions": [
                    {"transaction_id": "t2"},
                    {"transaction_id": "t3"},
                ],
                "total_transactions": 3,
            }
        raise AssertionError(f"unexpected offset {offset}")

    result = fetch_all_transaction_pages(fetch_page, page_size=1)
    assert calls == [0, 1]
    assert result["accounts"] == [{"account_id": "a1"}]
    assert result["item"] == {"item_id": "item-1"}
    assert result["request_id"] == "req-1"
    assert [t["transaction_id"] for t in result["transactions"]] == ["t1", "t2", "t3"]
    assert result["total_transactions"] == 3


def test_stops_on_empty_batch():
    def fetch_page(offset, count):
        if offset == 0:
            return {
                "accounts": [],
                "item": {},
                "request_id": "req",
                "transactions": [{"transaction_id": "t1"}],
                "total_transactions": 5,
            }
        return {
            "accounts": [],
            "item": {},
            "request_id": "req",
            "transactions": [],
            "total_transactions": 5,
        }

    result = fetch_all_transaction_pages(fetch_page, page_size=1)
    assert result["transactions"] == [{"transaction_id": "t1"}]
    assert result["total_transactions"] == 1
