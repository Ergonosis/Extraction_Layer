# Portal security notes

## Applying the schema (local)

PostgreSQL must be running. Then from the repo root:

```bash
set FLASK_APP=api.app:create_app
flask db upgrade
```

Use `DATABASE_URL` in `.env` if needed. Local default is `postgresql://portal:portal@localhost:5434/portal` (Docker `extraction-portal-postgres`). Do not use ports 5432/5433. Production uses Cloud SQL.

## Redis (sessions + rate limits)

Local default: Docker container `extraction-portal-redis` on host port **6379**.

```bash
docker run -d --name extraction-portal-redis -p 6379:6379 redis:7-alpine
```

`REDIS_URL` defaults to `redis://localhost:6379/0`. Flask-Session and flask-limiter both use this Redis. Production should point `REDIS_URL` at Memorystore (or equivalent), not a laptop container.

## CSRF

Mutating requests (`POST` / `PUT` / `DELETE` / `PATCH`) must send header `X-CSRF-Token` matching the token from `GET /api/auth/csrf-token` (stored in the server session). Missing/invalid token returns `403`.

## Session cookies

- `HttpOnly`, `SameSite=Lax`
- `Secure` defaults to on only when `FLASK_ENV=production` (override with `SESSION_COOKIE_SECURE`)
- Lifetime: 8 hours

## Loading secrets from GCP

Set `USE_GCP_SECRETS=true` and `GCP_PROJECT_ID=...`. Then `SECRET_KEY`, `FERNET_KEY`, and other secrets can be loaded from Secret Manager (`SECRET_KEY_SECRET_ID` overrides the secret name). Locally, keep using `.env`.

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

## Microsoft Entra SSO (portal login)

Register a **multi-tenant** app registration in Entra ID (“Accounts in any organizational directory”).

Redirect URI (web): `http://localhost:5175/api/auth/callback` for local portal + Vite `/api` proxy (so the session cookie is set on the SPA origin). Override with `MS_REDIRECT_URI` in production. Portal Vite uses port **5175** (`strictPort`) to avoid clashing with other apps on 5173.

Required app env vars:

- `MS_CLIENT_ID`
- `MS_CLIENT_SECRET` (Secret Manager in production)
- Optional: `MS_TENANT_ALLOWLIST` (comma-separated tenant IDs; empty = allow any org tenant)
- Optional: `PORTAL_URL` (default `http://localhost:5175`), `PORTAL_POST_LOGIN_PATH` (default `/connections`)

SSO uses authority `https://login.microsoftonline.com/organizations` and scopes `openid profile email`. The portal session stores only `user_id` and `organization_id` — the Microsoft SSO access token is **not** persisted.

Verify without a real Entra redirect:

```bash
python scripts/verify_portal_auth.py
```

## LOCAL ONLY — auth bypass (never in production)

Two **development-only** escapes exist so you can view the portal without Microsoft SSO.
Both must be **off** before any production / shared deployment.

### 1) API: `ENABLE_DEV_LOGIN` (real session, no Entra)

In repo-root `.env` (local only):

```env
FLASK_ENV=development
ENABLE_DEV_LOGIN=true
```

Then `POST /api/auth/dev-login` (with CSRF) creates a session as `dev@localhost`.

- App **refuses to start** if `ENABLE_DEV_LOGIN=true` and `FLASK_ENV=production`.
- Startup prints a loud stderr warning when enabled.
- `GET /api/health` and `GET /api/auth/dev-status` report `dev_login_enabled`.

### 2) SPA: `VITE_DEV_BYPASS_AUTH` (UI-only mock user)

In `portal/.env.local`:

```env
VITE_DEV_BYPASS_AUTH=true
```

Skips `AuthGuard` and injects a mock user so you can browse the shell without the API.
Integrations API still needs a real session (use #1) or you will see load errors.

### Pre-production checklist

- [ ] `ENABLE_DEV_LOGIN` unset or `false`
- [ ] `VITE_DEV_BYPASS_AUTH` unset or `false` (and not baked into a production build)
- [ ] `/api/health` shows `"dev_login_enabled": false`
- [ ] No orange **DEV AUTH BYPASS** banner in the UI
