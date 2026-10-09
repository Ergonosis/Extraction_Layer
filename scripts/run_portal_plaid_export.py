"""Run a real Plaid export for the local portal user and show the JSON file.

Prerequisites (repo root):
  - Postgres + Redis running (defaults in api/config.py)
  - Root `.env` with ENABLE_DEV_LOGIN=true, FERNET_KEY, PLAID_* sandbox keys
  - You already connected Plaid in the portal as the local dev user
    (Connections → Connect → sandbox Link, e.g. user_good / pass_good)

Usage:
  python scripts/run_portal_plaid_export.py
  python scripts/run_portal_plaid_export.py --start-date 2024-01-01 --end-date 2024-12-31
  python scripts/run_portal_plaid_export.py --window-days 30
  python scripts/run_portal_plaid_export.py --open   # open the file in the default editor/viewer

Never prints access tokens.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Load repo-root .env before create_app (Config also load_dotenv).
os.chdir(REPO_ROOT)


def _csrf(client) -> str:
    resp = client.get("/api/auth/csrf-token")
    if resp.status_code != 200:
        raise SystemExit(f"Could not get CSRF token: HTTP {resp.status_code}")
    return resp.get_json()["csrf_token"]


def _preview_export(path: Path, *, max_tx: int) -> None:
    if not path.is_file():
        print(f"\nFile not found on disk: {path}")
        return

    data = json.loads(path.read_text(encoding="utf-8"))
    accounts = data.get("accounts") or []
    transactions = data.get("transactions") or []
    item = data.get("item") or {}
    filters = data.get("filters") or {}

    print("\n========== Export preview ==========")
    print(f"File:         {path.resolve()}")
    print(f"Size:         {path.stat().st_size:,} bytes")
    print(f"Item id:      {item.get('item_id') or filters.get('item_id') or '(n/a)'}")
    print(f"Date filter:  {filters.get('start_date')} -> {filters.get('end_date')}")
    print(f"Accounts:     {len(accounts)}")
    print(f"Transactions: {len(transactions)} (total_transactions={data.get('total_transactions')})")

    if accounts:
        print("\nAccounts:")
        for acct in accounts[:8]:
            name = acct.get("name") or acct.get("official_name") or "(unnamed)"
            mask = acct.get("mask") or "????"
            subtype = acct.get("subtype") or acct.get("type") or ""
            print(f"  - {name} …{mask} ({subtype})")
        if len(accounts) > 8:
            print(f"  … and {len(accounts) - 8} more")

    if transactions:
        print(f"\nFirst {min(max_tx, len(transactions))} transactions:")
        for tx in transactions[:max_tx]:
            date = tx.get("date") or tx.get("authorized_date") or "?"
            name = tx.get("name") or tx.get("merchant_name") or "(no name)"
            amount = tx.get("amount")
            print(f"  {date}  {amount!s:>10}  {name}")
        if len(transactions) > max_tx:
            print(f"  … and {len(transactions) - max_tx} more")
    else:
        print("\nNo transactions in this file (try a wider date range).")

    print("====================================")
    print(f"\nOpen the full file with:\n  {path.resolve()}")


def _open_file(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export Plaid data via the portal API for the local dev user.",
    )
    parser.add_argument("--start-date", help="YYYY-MM-DD (optional)")
    parser.add_argument("--end-date", help="YYYY-MM-DD (optional)")
    parser.add_argument(
        "--window-days",
        type=int,
        help="Pull the last N days (optional; alternative to start/end)",
    )
    parser.add_argument(
        "--max-tx",
        type=int,
        default=15,
        help="How many transactions to print in the preview (default 15)",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open the export JSON in the system default app",
    )
    args = parser.parse_args()

    from api.app import create_app

    app = create_app()
    if not app.config.get("ENABLE_DEV_LOGIN"):
        print(
            "ENABLE_DEV_LOGIN must be true in .env so this script can sign in "
            "as the local portal user.",
            file=sys.stderr,
        )
        return 1
    if not (app.config.get("PLAID_CLIENT_ID") and app.config.get("PLAID_SECRET")):
        print(
            "Set PLAID_CLIENT_ID and PLAID_SECRET in .env (sandbox is fine).",
            file=sys.stderr,
        )
        return 1
    if not app.config.get("FERNET_KEY"):
        print("Set FERNET_KEY in .env (required to decrypt the stored Plaid token).", file=sys.stderr)
        return 1

    client = app.test_client()

    print("Signing in as local dev user…")
    csrf = _csrf(client)
    login = client.post("/api/auth/dev-login", headers={"X-CSRF-Token": csrf})
    if login.status_code != 200:
        print(f"dev-login failed: HTTP {login.status_code} {login.get_json()}", file=sys.stderr)
        return 1

    listing = client.get("/api/integrations/")
    if listing.status_code != 200:
        listing = client.get("/api/integrations")
    if listing.status_code != 200:
        print(f"Could not list integrations: HTTP {listing.status_code}", file=sys.stderr)
        return 1

    integrations = (listing.get_json() or {}).get("integrations") or []
    plaid = next((row for row in integrations if row.get("provider") == "plaid"), None)
    if plaid is None:
        print("No Plaid integration row found.", file=sys.stderr)
        return 1

    status = plaid.get("status")
    print(f"Plaid status: {status}  account={plaid.get('connected_account')!r}")
    if status not in ("connected", "reauth_required"):
        print(
            "\nPlaid is not connected for the local dev user.\n"
            "1) Start the portal (Vite :5175) + Flask API\n"
            "2) Sign in with “Continue as local dev user”\n"
            "3) Connections → Plaid → Connect → sandbox Link\n"
            "4) Re-run this script\n",
            file=sys.stderr,
        )
        return 1

    body: dict = {}
    if args.window_days is not None:
        body["window_days"] = args.window_days
    if args.start_date:
        body["start_date"] = args.start_date
    if args.end_date:
        body["end_date"] = args.end_date

    print("Calling POST /api/plaid/export (real Plaid sandbox pull)…")
    csrf = _csrf(client)
    resp = client.post(
        "/api/plaid/export",
        json=body or {},
        headers={"X-CSRF-Token": csrf},
    )
    payload = resp.get_json(silent=True) or {}
    if resp.status_code != 200:
        print(
            f"Export failed: HTTP {resp.status_code}\n{json.dumps(payload, indent=2)}",
            file=sys.stderr,
        )
        if resp.status_code == 401:
            print(
                "Hint: status may be reauth_required — reconnect Plaid in the portal.",
                file=sys.stderr,
            )
        return 1

    file_path = payload.get("file")
    item_id = payload.get("item_id")
    print(f"Export OK. item_id={item_id}")
    print(f"API returned file path: {file_path}")

    if not file_path:
        print("No file path in response.", file=sys.stderr)
        return 1

    path = Path(file_path)
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()

    _preview_export(path, max_tx=args.max_tx)

    if args.open:
        print("\nOpening file…")
        _open_file(path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
