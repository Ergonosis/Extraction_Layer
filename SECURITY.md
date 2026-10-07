# Portal security notes

## Applying the schema (local)

PostgreSQL must be running. Then from the repo root:

```bash
set FLASK_APP=api.app:create_app
flask db upgrade
```

Use `DATABASE_URL` in `.env` if needed. Local default is `postgresql://portal:portal@localhost:5434/portal` (Docker `extraction-portal-postgres`). Do not use ports 5432/5433. Production uses Cloud SQL.

## Fernet key (`FERNET_KEY`)

Plaid and Microsoft Graph tokens are encrypted at rest with Fernet (symmetric AES). The key lives in **Google Cloud Secret Manager** in production. Local development may use a `.env` value; that is not acceptable in production.

Generate a key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Store the output in Secret Manager (and locally in `.env` for dev only). Never commit the key. Never log plaintext tokens or the key.

## Rotating `FERNET_KEY`

1. Generate a **new** Fernet key and store it in Secret Manager as a new secret version (keep the old version readable).
2. Temporarily load **both** keys in a one-off script: decrypt each `plaid_credentials.access_token_enc` and `ms_graph_credentials.access_token_enc` / `refresh_token_enc` with the old key, re-encrypt with the new key, and write the rows back.
3. Point the app at the new key only.
4. Disable the old Secret Manager version after a successful decrypt check on a sample row.

If the only copy of `FERNET_KEY` is lost, stored tokens cannot be recovered. Users must reconnect Plaid and Microsoft Graph.

## Flask `SECRET_KEY`

Used to sign sessions. Load from Secret Manager in production. Rotating it invalidates existing sessions (users sign in again). That is expected.
