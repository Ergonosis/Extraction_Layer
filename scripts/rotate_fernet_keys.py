"""Fernet key rotation dry-run / apply for portal credential rows (issue #28).

Usage (from repo root):

  # Dry-run: decrypt with OLD key, re-encrypt with NEW, do not write
  set FERNET_KEY=<old-key>
  set FERNET_NEW_KEY=<new-key>
  python scripts/rotate_fernet_keys.py --dry-run

  # Apply: rewrite ciphertext with NEW key (keep OLD in FERNET_PREVIOUS_KEYS
  # on the app until all rows are verified, then drop previous keys)
  python scripts/rotate_fernet_keys.py --apply

Never logs plaintext tokens.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Rotate portal Fernet token keys")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Verify decrypt/re-encrypt only")
    mode.add_argument("--apply", action="store_true", help="Write re-encrypted blobs")
    args = parser.parse_args()

    old_key = (os.environ.get("FERNET_KEY") or "").strip()
    new_key = (os.environ.get("FERNET_NEW_KEY") or "").strip()
    if not old_key or not new_key:
        print("Set FERNET_KEY (current/old) and FERNET_NEW_KEY (next)", file=sys.stderr)
        return 2
    if old_key == new_key:
        print("FERNET_NEW_KEY must differ from FERNET_KEY", file=sys.stderr)
        return 2

    from cryptography.fernet import Fernet, InvalidToken

    old_f = Fernet(old_key.encode("utf-8") if isinstance(old_key, str) else old_key)
    new_f = Fernet(new_key.encode("utf-8") if isinstance(new_key, str) else new_key)

    from api.app import create_app
    from api.extensions import db
    from api.models import MsGraphCredential, PlaidCredential

    app = create_app()
    updated = 0
    checked = 0
    failures = 0

    with app.app_context():
        rows: list[tuple[str, object, str]] = []
        for cred in PlaidCredential.query.all():
            rows.append(("plaid.access_token_enc", cred, "access_token_enc"))
        for cred in MsGraphCredential.query.all():
            rows.append(("msgraph.access_token_enc", cred, "access_token_enc"))
            rows.append(("msgraph.refresh_token_enc", cred, "refresh_token_enc"))

        for label, obj, attr in rows:
            blob = getattr(obj, attr)
            checked += 1
            try:
                plaintext = old_f.decrypt(blob)
                new_blob = new_f.encrypt(plaintext)
                # Prove new blob decrypts; never print plaintext.
                new_f.decrypt(new_blob)
            except InvalidToken:
                print(f"FAIL: cannot decrypt {label} id={getattr(obj, 'id', '?')}")
                failures += 1
                continue
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL: {label} id={getattr(obj, 'id', '?')}: {type(exc).__name__}")
                failures += 1
                continue

            if args.apply:
                setattr(obj, attr, new_blob)
                updated += 1

        if args.apply and failures == 0:
            db.session.commit()
            print(f"Applied re-encryption to {updated} field(s); checked {checked}")
            print("Next: set app FERNET_KEY to the new key; keep old in FERNET_PREVIOUS_KEYS")
            print("until a sample decrypt succeeds in production, then remove previous keys.")
        elif args.apply:
            db.session.rollback()
            print(f"Aborted apply due to {failures} failure(s); no rows written")
            return 1
        else:
            print(
                f"Dry-run OK for {checked - failures}/{checked} field(s); "
                f"failures={failures}"
            )
            if failures:
                return 1
            print("Re-run with --apply to write new ciphertext.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
