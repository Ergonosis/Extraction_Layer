import plaid
from plaid.api import plaid_api
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions
from extractors.export_helpers import (
    build_export_filename,
    filter_accounts_and_transactions,
    resolve_date_range,
    resolve_export_prefix,
    strip_balances,
    write_export,
)
from extractors.plaid_pagination import fetch_all_transaction_pages
from paths import get_records_dir

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
    def fetch_page(offset, count):
        options = TransactionsGetRequestOptions(count=count, offset=offset)
        request = TransactionsGetRequest(
            access_token=access_token,
            start_date=start_date,
            end_date=end_date,
            options=options,
        )
        return client.transactions_get(request).to_dict()

    return fetch_all_transaction_pages(fetch_page)


def _fetch_accounts_only(client, access_token):
    response = client.accounts_get(AccountsGetRequest(access_token=access_token)).to_dict()
    return response.get("accounts", []), response.get("item", {}), response.get("request_id")


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
    start_date, end_date = resolve_date_range(
        start_date=start_date,
        end_date=end_date,
        is_hard_pull=is_hard_pull,
        window_days=window_days,
    )

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

    filtered_accounts, filtered_transactions = filter_accounts_and_transactions(
        data.get("accounts", []),
        data.get("transactions", []),
        account_filter,
    )

    if not include_balances:
        filtered_accounts = strip_balances(filtered_accounts)

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

    prefix = resolve_export_prefix(
        is_hard_pull=is_hard_pull,
        window_days=window_days,
        prefix=prefix,
    )
    output_dir = output_dir or get_records_dir()
    filename = build_export_filename(
        output_dir, prefix, start_date, end_date, item_id=item_id
    )
    return write_export(data, filename)
