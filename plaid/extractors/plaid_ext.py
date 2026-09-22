import json
import os
from datetime import date, timedelta
import plaid
from plaid.api import plaid_api
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions
from extractors.matching import matches_any

class PlaidExtractor:
    def __init__(self, client_id, secret, env):
        host = plaid.Environment.Sandbox
        if env == 'development': host = plaid.Environment.Development
        elif env == 'production': host = plaid.Environment.Production

        configuration = plaid.Configuration(
            host=host,
            api_key={'clientId': client_id, 'secret': secret}
        )
        api_client = plaid.ApiClient(configuration)
        self.client = plaid_api.PlaidApi(api_client)

def _fetch_transactions_paginated(client, access_token, start_date, end_date):
    offset = 0
    count = 500
    all_transactions = []
    accounts = []
    item = {}
    request_id = None
    total_transactions = 0

    while True:
        options = TransactionsGetRequestOptions(count=count, offset=offset)
        request = TransactionsGetRequest(
            access_token=access_token,
            start_date=start_date,
            end_date=end_date,
            options=options,
        )

        response = client.transactions_get(request).to_dict()
        batch = response.get("transactions", [])

        if not accounts:
            accounts = response.get("accounts", [])
        if not item:
            item = response.get("item", {})
        if request_id is None:
            request_id = response.get("request_id")

        total_transactions = response.get("total_transactions", len(batch))
        all_transactions.extend(batch)
        offset += len(batch)

        if offset >= total_transactions:
            break

    return {
        "accounts": accounts,
        "transactions": all_transactions,
        "item": item,
        "total_transactions": len(all_transactions),
        "request_id": request_id,
    }


def _fetch_accounts_only(client, access_token):
    response = client.accounts_get(AccountsGetRequest(access_token=access_token)).to_dict()
    return response.get("accounts", []), response.get("item", {}), response.get("request_id")


def _account_matches(account, account_filter):
    return matches_any(
        account_filter,
        account.get("account_id", ""),
        account.get("name", ""),
        account.get("official_name", ""),
        account.get("mask", ""),
        account.get("subtype", ""),
        account.get("type", ""),
    )


def _strip_balances(accounts):
    sanitized = []
    for account in accounts:
        copy = dict(account)
        copy.pop("balances", None)
        sanitized.append(copy)
    return sanitized


def fetch_and_store(
    client,
    access_token,
    item_id=None,
    is_hard_pull=False,
    window_days=None,
    start_date=None,
    end_date=None,
    prefix=None,
    include_transactions=True,
    include_balances=True,
    account_filter=None,
    output_dir=None,
):
    if end_date is None:
        end_date = date.today()

    if start_date is None:
        if is_hard_pull:
            start_date = date(2000, 1, 1)
        else:
            days = window_days if window_days is not None else 7
            if days <= 0:
                raise ValueError("window_days must be greater than 0")
            start_date = end_date - timedelta(days=days)

    if start_date > end_date:
        raise ValueError("start_date must be on or before end_date")

    if include_transactions:
        data = _fetch_transactions_paginated(client, access_token, start_date, end_date)
    else:
        accounts, item, request_id = _fetch_accounts_only(client, access_token)
        data = {
            "accounts": accounts,
            "transactions": [],
            "item": item,
            "total_transactions": 0,
            "request_id": request_id,
        }

    selected_account_ids = {
        account.get("account_id")
        for account in data.get("accounts", [])
        if _account_matches(account, account_filter)
    }
    filtered_accounts = [
        account
        for account in data.get("accounts", [])
        if account.get("account_id") in selected_account_ids
    ]
    filtered_transactions = [
        txn
        for txn in data.get("transactions", [])
        if txn.get("account_id") in selected_account_ids
    ]

    if not include_balances:
        filtered_accounts = _strip_balances(filtered_accounts)

    data["accounts"] = filtered_accounts
    data["transactions"] = filtered_transactions
    data["total_transactions"] = len(filtered_transactions)
    data["filters"] = {
        "start_date": str(start_date),
        "end_date": str(end_date),
        "item_id": item_id,
        "account_filter": account_filter,
        "include_transactions": include_transactions,
        "include_balances": include_balances,
    }

    if prefix is None:
        if is_hard_pull:
            prefix = "full_history"
        elif window_days is not None:
            prefix = "weekly"
        else:
            prefix = "range"

    item_suffix = f"_{item_id}" if item_id else ""
    output_dir = output_dir or os.getenv("RECORDS_DIR", "records")
    filename = os.path.join(output_dir, f"{prefix}_{start_date}_to_{end_date}{item_suffix}.json")
    os.makedirs(output_dir, exist_ok=True)

    with open(filename, "w") as f:
        json.dump(data, f, indent=4, default=str)

    return filename
