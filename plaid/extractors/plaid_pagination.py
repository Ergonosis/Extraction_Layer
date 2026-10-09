"""Plaid transaction page accumulation (no Plaid SDK)."""


def fetch_all_transaction_pages(fetch_page, page_size=500):
    """
    Walk paginated transaction responses.

    fetch_page(offset, count) must return a dict with keys like
    transactions, accounts, item, request_id, total_transactions.
    """
    first = fetch_page(0, page_size)
    accounts = first.get("accounts", [])
    item = first.get("item", {})
    request_id = first.get("request_id")
    batch = first.get("transactions", [])
    all_transactions = list(batch)
    offset = len(batch)
    total_transactions = first.get("total_transactions", len(batch))

    while offset < total_transactions and batch:
        page = fetch_page(offset, page_size)
        batch = page.get("transactions", [])
        all_transactions.extend(batch)
        offset += len(batch)

    return {
        "accounts": accounts,
        "transactions": all_transactions,
        "item": item,
        "total_transactions": len(all_transactions),
        "request_id": request_id,
    }
