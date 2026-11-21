# Deploy portal to GCP + Firebase

**Target layout**

| Piece | Role |
|---|---|
| **Firebase Hosting** | Static SPA (`portal/dist`), CDN, independent frontend releases |
| **Cloud Run** | API-only image, multiple instances |
| **Cloud SQL PostgreSQL** | Business data + server-side sessions + rate limits + session revocations |

Same-origin cookies work because Hosting rewrites `/api/**` to Cloud Run and the session cookie is named `__session` (Firebase forwards that name).

**Not used for first launch:** Memorystore Redis, VPC Connector, Cloud Storage, workers/queues, Cloud Armor. SQL networking uses **Direct VPC egress** (private IP + Auth Proxy sidecar), not a VPC Connector.

## What is in git

| Path | Role |
|---|---|
| `infra/portal/Dockerfile` | API-only Python/gunicorn image (no SPA) |
| `infra/portal/cloudrun.yaml` | Cloud Run Service spec (image digest patched by CI) |
| `firebase.json` / `.firebaserc` | Hosting public dir, `/api/**` → Cloud Run, SPA fallback, CSP |
| `.github/workflows/deploy-portal-backend.yaml` | Build, migrate Job, deploy API (WIF) |
| `.github/workflows/deploy-portal-frontend.yaml` | Build SPA and `firebase deploy --only hosting` |
| `deploy/check-cloud-sql-ready.sh` | Preflight: SQL RUNNABLE + secrets ENABLED (no secret values) |
| `deploy/migrate-cloud-run-job.sh` + `deploy/render-sql-job.py` | `flask db upgrade` as a Cloud Run Job (same image digest) |
| `deploy/env.migrate.example` | Manual migrate Job variables |
| `deploy/build-portal-local.sh` / `.ps1` | Local `portal/dist` build (bun) |

`.env.dev` is the committed, non-secret source for `CLOUD_SQL_INSTANCE` and related deploy names used by workflows.

## Dedicated Portal Entra app (required for SSO)

Create a **new** multi-tenant Microsoft Entra app registration used **only** by Extraction Layer. Do **not** change the shared `Ergonosis_data_getter` app (`d0130a30-5dad-4987-b43e-d559aa82871b`) or its job secrets.

1. Supported account types: accounts in any organizational directory (multi-tenant), matching authority `https://login.microsoftonline.com/organizations`.
2. Web redirect URIs:
   - `https://ergonosis-extraction-portal.web.app/api/auth/callback`
   - `https://ergonosis-extraction-portal.web.app/api/msgraph/callback`
   - Local: `http://localhost:5175/api/auth/callback`, `http://localhost:5175/api/msgraph/callback`
3. Delegated permissions (admin consent as required): `User.Read`, `Mail.Read`, `Calendars.Read`, `Files.Read`.
4. Create a client secret for this Portal app only.
5. Store Portal values in Secret Manager / env as `MSGRAPH_CLIENT_ID` and `MSGRAPH_CLIENT_SECRET` (Portal-specific versions — not the shared job credentials).
6. Confirm `infra/portal/cloudrun.yaml` has:
   - `MS_AUTHORITY=https://login.microsoftonline.com/organizations`
   - `MS_REDIRECT_URI` / `MS_GRAPH_REDIRECT_URI` on the Hosting origin
7. Optional: `MS_TENANT_ALLOWLIST` for an explicit tenant allowlist.

Acceptance: browser SSO, consent, optional tenant allowlist, and Graph connect succeed against the **Portal** app; shared job registration remains untouched.

## One-time GCP / Firebase setup

1. **Project + APIs:** Cloud Run, Artifact Registry, Cloud SQL Admin, Secret Manager, Firebase Hosting.
2. **Artifact Registry** (Docker) for the API image.
3. **Cloud SQL (Postgres)** private IP, Direct VPC egress from Cloud Run (no VPC Connector).
4. **Runtime service account** with `secretmanager.secretAccessor` and `cloudsql.client`.
5. **Secrets** in Secret Manager (Portal names): `EXTRACTION_PORTAL_FLASK_SECRET_KEY`, `EXTRACTION_PORTAL_FERNET_KEY`, `EXTRACTION_PORTAL_DATABASE_URL`, `MSGRAPH_CLIENT_ID`, `MSGRAPH_CLIENT_SECRET`, `PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ENV`.
6. **Firebase:** `.firebaserc` project; `firebase.json` `run.serviceId` / `region` aligned with Cloud Run.
7. **GitHub WIF** bindings for the repository (backend + Firebase deploy SA as configured in workflows).

## Release order

Automated on `main` via GitHub Actions:

1. Backend workflow: lock check → pytest → critical Ruff → build/push image → migrate Job (same digest) → `gcloud run services replace` with digest.
2. Frontend workflow: bun build → `firebase deploy --only hosting`.

Manual migrate (break-glass):

```bash
set -a && source deploy/env.migrate.local && set +a
bash deploy/migrate-cloud-run-job.sh
```

## Frontend (local)

```bash
bash deploy/build-portal-local.sh
# or: cd portal && bun install --frozen-lockfile && bun run build
firebase deploy --only hosting
```

## Connection budget

`max instances × gunicorn workers × (DB_POOL_SIZE + DB_MAX_OVERFLOW)` must stay under the Cloud SQL connection limit (leave headroom for the migrate Job and overlapping revisions). Production defaults in `cloudrun.yaml` target a ~45/100 model.

## Verify after deploy

```bash
curl -sS "$PORTAL_URL/api/health"
curl -sS "$PORTAL_URL/api/ready"
```

Expect health `"status":"ok"` with `dev_login_enabled: false` in production. Confirm logout cannot resurrect a SID (session revocations), and Hosting `/api/**` still proxies to Cloud Run.

## Related

- `SECURITY.md` — sessions, secrets, tenancy, CSP
- Issue #61 — PR #58 follow-ups (revocation, Portal Entra, workflow/docs)
- Issue #56 / PR #57 — Firebase + Cloud SQL shared-state baseline
