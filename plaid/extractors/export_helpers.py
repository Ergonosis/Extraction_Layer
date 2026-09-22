"""Pure helpers for Plaid export shaping and file write (no Plaid SDK)."""

import json
import os
from datetime import date, timedelta

from extractors.matching import matches_any


def resolve_date_range(start_date=None, end_date=None, is_hard_pull=False, window_days=None):
    end_date = end_date or date.today()
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
    return start_date, end_date


def account_matches(account, account_filter):
    return matches_any(
        account_filter,
        account.get("account_id", ""),
        account.get("name", ""),
        account.get("official_name", ""),
        account.get("mask", ""),
        account.get("subtype", ""),
        account.get("type", ""),
    )


def filter_accounts_and_transactions(accounts, transactions, account_filter=None):
    filtered_accounts = [a for a in accounts if account_matches(a, account_filter)]
    selected_ids = {a.get("account_id") for a in filtered_accounts}
    filtered_transactions = [
        t for t in transactions if t.get("account_id") in selected_ids
    ]
    return filtered_accounts, filtered_transactions


def strip_balances(accounts):
    sanitized = []
    for account in accounts:
        copy = dict(account)
        copy.pop("balances", None)
        sanitized.append(copy)
    return sanitized


def resolve_export_prefix(is_hard_pull=False, window_days=None, prefix=None):
    if prefix is not None:
        return prefix
    if is_hard_pull:
        return "full_history"
    if window_days is not None:
        return "weekly"
    return "range"


def build_export_filename(output_dir, prefix, start_date, end_date, item_id=None):
    item_suffix = f"_{item_id}" if item_id else ""
    return os.path.join(
        output_dir, f"{prefix}_{start_date}_to_{end_date}{item_suffix}.json"
    )


def write_export(data, filename):
    parent = os.path.dirname(filename)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(filename, "w") as f:
        json.dump(data, f, indent=4, default=str)
    return filename
