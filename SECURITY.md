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

**Scale note:** multiple Cloud Run instances require shared Redis sessions. Without Redis, sticky sessions alone will not keep logins consistent across instances.

## Multi-organization tenancy (issue #30)

The portal uses **shared-schema** tenancy: one Cloud SQL / Postgres database, every tenant row tagged with `organization_id`. There is no database-per-customer.

### Mapping

| Concept | Storage |
|---|---|
| Microsoft Entra tenant (`tid` claim) | `organizations.ms_tenant_id` (unique) |
| Signed-in person (`oid` claim) | `users` row scoped by `(organization_id, ms_oid)` |
| Plaid / MS Graph connection | `integrations` row per `(user_id, provider)`, also stamped with `organization_id` |

SSO (`complete_sso_login`) finds or creates the org from `tid`, then finds or creates the user in that org. The session stores only `user_id` and `organization_id`. Portal SSO authority is `https://login.microsoftonline.com/organizations` — **not** a single `MS_TENANT_ID`. Optional `MS_TENANT_ALLOWLIST` restricts which Entra tenants may sign in.

### Isolation rules

- `login_required` rejects sessions whose `organization_id` does not match the user row.
- Integrations / Plaid / MS Graph services load rows with **both** `user_id` and `organization_id`.
- `ensure_provider_rows` calls `require_matching_org` so a mismatched id pair fails closed (HTTP 403).
- Plaid and Graph tokens stay **per-user inside an org** (delegated consent). They are not shared org-wide.
- Out of scope for #30: org admin UI, invites, roles, DB-per-tenant.

### GCP cost tiers (planning)

Rough monthly GCP cost for the portal stack (Cloud Run + Cloud SQL + Redis/Memorystore). **Plaid usage is billed separately.**

| Tier | Approx. GCP / month | Shape |
|---|---|---|
| Small | ~$40–90 | Single Cloud Run service, small Cloud SQL, Redis/Memorystore |
| Medium | ~$150–400 | Multi-instance Cloud Run, larger SQL, Memorystore |
| Large | ~$500–2,000 | HA Cloud SQL, more Redis capacity, autoscaling |

Production checklist for multi-instance scale:

- [ ] `REDIS_URL` points at Memorystore (shared sessions + rate limits)
- [ ] `DATABASE_URL` points at Cloud SQL (shared schema; org isolation in queries)
- [ ] Secrets via Secret Manager (`USE_GCP_SECRETS=true`)
- [ ] `MS_TENANT_ALLOWLIST` set if you must restrict which companies can sign in

```bash
python scripts/verify_portal_tenancy.py
```

### GCP deploy scripts (issue #48)

Build/push/migrate/deploy tooling lives under `deploy/` (Dockerfile at repo root). See **[docs/deploy-gcp.md](docs/deploy-gcp.md)** for Cloud Run + Secret Manager steps.

## Production GCP hardening (issue #33)

App-layer cookies/CSRF/rate limits/Fernet are covered by #20 / #28. This section covers **network posture, SPA CSP, audit logs, and monitoring**. Cloud Armor / WAF is **deferred** (see below).

### Private Redis + Cloud SQL

| Resource | Production pattern |
|---|---|
| Cloud SQL | Private IP **or** Unix socket via Cloud SQL connector: `postgresql://USER:PASS@/DB?host=/cloudsql/PROJECT:REGION:INSTANCE` |
| Memorystore | Private VPC IP, e.g. `redis://10.x.x.x:6379/0` (enable AUTH when available); **not** a public `:6379` |
| Cloud Run | Serverless VPC Access connector + `--vpc-egress=private-ranges-only` so the service can reach SQL/Redis |
| Secrets | `USE_GCP_SECRETS=true`, runtime SA with `roles/secretmanager.secretAccessor` + `roles/cloudsql.client` only |

TLS terminates at Cloud Run / HTTPS load balancer. Production boot requires `SESSION_COOKIE_SECURE=true` (see `api/app.py`). Never set `ENABLE_DEV_LOGIN` in production.

### Content-Security-Policy (SPA)

Because the SPA is served from the same Cloud Run origin (`PORTAL_STATIC_DIR`), Flask sets CSP on every response in `api/middleware.py`.

| `CSP_MODE` | Behavior |
|---|---|
| *(empty)* | `enforce` when `FLASK_ENV=production`, else `report-only` |
| `report-only` | `Content-Security-Policy-Report-Only` (safe to test) |
| `enforce` | `Content-Security-Policy` |
| `off` | No CSP header |

Default policy (`api/csp.py`) allows `'self'` plus Plaid Link and Microsoft login/Graph hosts. Override with `CSP_POLICY` only if you know you need a different allowlist. After changing CSP, re-test Connect flows for Plaid and Entra.

### Audit logging

Structured JSON lines go to logger `portal.audit` (stdout → Cloud Logging on Cloud Run). Helper: `api/audit.py` → `audit(event, user_id=..., organization_id=..., **extra)`.

Events include: `auth.login.success` / `auth.login.failure` / `auth.logout`, `org.created` / `user.created`, `plaid.connect.*` / `plaid.disconnect` / `plaid.export`, `msgraph.connect.*` / `msgraph.disconnect` / `msgraph.permissions.*` / `msgraph.export`.

**Never** put tokens, cookies, CSRF values, or Fernet material in audit fields (keys containing those substrings are stripped).

### Recommended Cloud Logging alert (at least one)

Create a log-based metric + alerting policy on:

```text
jsonPayload.event="auth.login.failure"
OR textPayload:"auth.login.failure"
```

(Adjust for your Cloud Run log format — many setups parse JSON stdout into `jsonPayload`.) Alert when count exceeds a small threshold over 5–15 minutes (auth abuse / credential stuffing). Optional second alert: spike of HTTP `429` or `403` on `/api/auth/*`.

Also watch Cloud Monitoring for Cloud SQL / Memorystore connectivity errors and Secret Manager access denials.

### Cloud Armor / WAF — deferred

**Decision (issue #33):** defer Cloud Armor until a public multi-tenant launch. App-level `flask-limiter` remains the primary rate control. Revisit Armor (edge bot/IP rules) when exposing a custom domain to the open internet; document any policy alongside this section.

```bash
python scripts/verify_portal_security_audit.py
```

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

App decrypt supports a rotation window: primary `FERNET_KEY` plus optional comma-separated `FERNET_PREVIOUS_KEYS` (decrypt-only fallbacks via `MultiFernet`). Encrypt always uses the primary key.

### Dry-run / apply script

```bash
# Generate new key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Dry-run (no DB writes): current key decrypts, new key re-encrypts in memory
set FERNET_KEY=<current-key>
set FERNET_NEW_KEY=<new-key>
python scripts/rotate_fernet_keys.py --dry-run

# Apply re-encryption to all Plaid + MS Graph credential blobs
python scripts/rotate_fernet_keys.py --apply
```

### Production cutover

1. Store the new key in Secret Manager; keep the old version readable.
2. Run `--dry-run`, then `--apply` against the DB.
3. Point the app `FERNET_KEY` at the new key; set `FERNET_PREVIOUS_KEYS` to the old key briefly.
4. Confirm a sample `decrypt_token` / status refresh succeeds.
5. Clear `FERNET_PREVIOUS_KEYS` and disable the old Secret Manager version.

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

## Plaid Link lifecycle (`/api/plaid/*`)

- `POST /connect` (10/min), `POST /exchange` (5/min), `POST /disconnect` (5/min) require login + CSRF.
- `GET /status` (15/min) requires login; never returns access tokens.
- Access tokens are Fernet-encrypted into `plaid_credentials.access_token_enc` before any DB write. Plaintext exists only in memory for Plaid API calls.
- Local/sandbox: set `PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ENV=sandbox`, and `FERNET_KEY`.

```bash
python scripts/verify_portal_plaid.py
```

## MS Graph lifecycle (`/api/msgraph/*`)

- `POST /connect` (10/min) validates scopes against the hardcoded allowlist, stores OAuth `state` in session, returns `authorize_url`. CSRF required.
- `GET /callback` (5/min) exchanges the auth code; Fernet-encrypts access + refresh tokens before DB write; upserts `ms_graph_permissions`.
- `POST /disconnect` (5/min) deletes credentials **without decrypting** and clears permissions. CSRF required.
- `GET /status` (15/min) refreshes via MSAL; re-encrypts rotated tokens; sets `reauth_required` on failure. Never returns tokens.
- Register `MS_GRAPH_REDIRECT_URI` (default `http://localhost:5175/api/msgraph/callback`) in the Entra app.

```bash
python scripts/verify_portal_msgraph.py
```

### Permission selector (issue #26)

- `GET /permissions/available` (30/min): allowlist + `is_active` flags.
- `PUT /permissions` (10/min, CSRF): toggle `is_active` for already-granted scopes; if new scopes are needed, returns `consent_required` + `redirect_url` for incremental consent.

```bash
python scripts/verify_portal_msgraph_permissions.py
```

### Data export wiring (issue #27)

- `POST /api/plaid/export` (10/min, CSRF): decrypts the Plaid access token in memory, calls legacy `plaid/extractors/plaid_ext.fetch_and_store`, returns file path / item metadata only.
- `POST /api/msgraph/export` (10/min, CSRF): decrypts the Graph access token in memory, calls `microsoft/ms_graph_email_client.py` (profile / mail / calendar). Request `include_*` flags are a wish list; pulls are gated by `scopes_granted` ∩ `is_active`.
- Plaintext tokens must never appear in responses, logs, or export JSON.

```bash
python scripts/verify_portal_exports.py
```

## LOCAL ONLY — auth bypass (never in production)

One development escape lets you use the portal without Microsoft SSO:

### `ENABLE_DEV_LOGIN` (real session, no Entra)

In repo-root `.env` (local only):

```env
FLASK_ENV=development
ENABLE_DEV_LOGIN=true
```

Then the login page shows **Continue as local dev user**, which calls `POST /api/auth/dev-login` and creates a session as `dev@localhost`.

- App **refuses to start** if `ENABLE_DEV_LOGIN=true` and `FLASK_ENV=production`.
- Startup prints a loud stderr warning when enabled.
- `GET /api/health` and `GET /api/auth/dev-status` report `dev_login_enabled`.
- Orange **DEV AUTH BYPASS** banner appears in the UI while enabled.

### Pre-production checklist

- [ ] `ENABLE_DEV_LOGIN` unset or `false`
- [ ] `/api/health` shows `"dev_login_enabled": false`
- [ ] No orange **DEV AUTH BYPASS** banner in the UI

## Security hardening audit (issue #28)

Verified locally with `python scripts/verify_portal_security_audit.py` (and prior issue scripts). Gaps closed in this issue are called out below.

### Cookies / sessions

| Check | Status |
|---|---|
| `HttpOnly`, `SameSite=Lax` | Verified (config) |
| `Secure` in production | Enforced by production boot guard + default when `FLASK_ENV=production` |
| 8h session lifetime → `/auth/me` 401 when expired | Lifetime configured 8h; logout / missing session returns 401 |
| Session ID changes after `/auth/callback` | `regenerate_session()` on SSO + dev-login |
| Logout destroys server-side session | `destroy_session()` deletes Redis key + rotates sid |

### CSRF

| Check | Status |
|---|---|
| POST/PUT/DELETE/PATCH require `X-CSRF-Token` → 403 | Verified |
| GET does not require CSRF | Verified |
| Axios interceptor sends CSRF on mutations | `portal/src/api/client.ts` |

### Rate limits

| Endpoint class | Limit |
|---|---|
| Default / reads | 30/min |
| `/auth/login` | 10/min |
| Auth/Graph callbacks, Plaid exchange/disconnect | 5/min |
| Mutations (connect, export, permissions, logout) | 10/min |
| Plaid/MS Graph status | 15/min |
| Burst → 429 | Verified |

### Encryption / secrets

| Check | Status |
|---|---|
| No endpoint returns tokens/secrets/keys | Audited (`/auth/me`, integrations, exports) |
| Production loads secrets via Secret Manager | Boot refuses production without `USE_GCP_SECRETS`, real `SECRET_KEY`, `FERNET_KEY`, `SESSION_COOKIE_SECURE` |
| Fernet rotation dry-run | `scripts/rotate_fernet_keys.py` + `FERNET_PREVIOUS_KEYS` |

### Response security

| Check | Status |
|---|---|
| HSTS, nosniff, DENY frame, Referrer-Policy | Middleware |
| Errors never leak stack/SQL/paths/keys | Generic JSON 500 handler; DEBUG/PROPAGATE off |
| CORS restricted to portal origins | `CORS_ORIGINS` (default localhost:5175) |

### Input validation

| Check | Status |
|---|---|
| Reject unexpected JSON fields → 400 | Plaid/MS Graph mutation bodies allowlisted |
| Enums / lengths / structure | Existing scope allowlists + public_token checks |
| OAuth `state` single-use | SSO + MS Graph callbacks `session.pop` state before exchange |

```bash
python scripts/verify_portal_security.py
python scripts/verify_portal_security_audit.py
```
