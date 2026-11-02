# Deploy portal to GCP + Firebase (issue #56)

**Target first-launch layout**

| Piece | Role |
|---|---|
| **Firebase Hosting** | Static SPA (`portal/dist`), CDN, independent frontend releases |
| **Cloud Run** | API-only image, multiple instances |
| **Cloud SQL PostgreSQL** | Business data + server-side sessions + shared rate-limit counters |

Same-origin cookies work because Hosting rewrites `/api/**` to Cloud Run and the session cookie is named `__session` (Firebase forwards that name).

**Deferred for first launch:** Memorystore Redis, VPC Connector (unless you opt into Redis backends), Cloud Storage, workers/queues, Cloud Armor.

## What is in git

| Path | Role |
|---|---|
| `Dockerfile` | API-only Python/gunicorn image (no SPA) |
| `firebase.json` / `.firebaserc` | Hosting public dir, `/api/**` → Cloud Run, SPA fallback, CSP |
| `deploy/cloudbuild.yaml` | Build/push API image to Artifact Registry |
| `deploy/migrate-cloud-run-job.sh` | `flask db upgrade` as a Cloud Run Job (same image digest) |
| `deploy/deploy-cloud-run.sh` | Deploy API service with prod env + Secret Manager mounts |
| `deploy/build-portal-local.sh` / `.ps1` | Build `portal/dist` for Hosting |
| `deploy/env.deploy.example` | Variable names only (copy locally; never commit secrets) |

## One-time GCP / Firebase setup

1. **Project + APIs:** Cloud Run, Artifact Registry, Cloud SQL Admin, Secret Manager, Firebase Hosting.
2. **Artifact Registry** (Docker) for the API image.
3. **Cloud SQL (Postgres)** in the same region. Prefer Cloud Run’s built-in Cloud SQL connection (Unix socket `/cloudsql/INSTANCE_CONNECTION_NAME`) with public IP enabled on the instance for first launch — no VPC Connector required for that path.
4. **Service account** for Cloud Run with:
   - `roles/secretmanager.secretAccessor`
   - `roles/cloudsql.client`
5. **Secrets** in Secret Manager: `SECRET_KEY`, `FERNET_KEY`, `MS_CLIENT_SECRET`, `PLAID_SECRET` (as needed).
6. **Firebase:** set `.firebaserc` project id; align `firebase.json` `run.serviceId` / `region` with the Cloud Run service.
7. **Entra app:** register production redirect URIs on the **Firebase Hosting** origin:
   - `https://<hosting>/api/auth/callback`
   - `https://<hosting>/api/msgraph/callback`

## Release order (first launch)

1. Build/push API image (digest).
2. Run migrate Job with that digest (`flask db upgrade`) — creates business + `sessions` + `rate_limit_buckets` tables.
3. Deploy Cloud Run service; wait until Ready; check `/api/health`.
4. `cd portal && npm ci && npm run build`
5. `firebase deploy --only hosting`

Later: frontend-only changes stop at step 4–5. API-only changes use 1–3.

## Build API image

```bash
gcloud builds submit --config deploy/cloudbuild.yaml \
  --substitutions=_REGION=us-central1,_REPO=portal,_IMAGE=extraction-portal
```

Local Docker smoke (API only):

```bash
docker build -t extraction-portal:local .
docker run --rm -p 8080:8080 \
  -e FLASK_ENV=development \
  -e ENABLE_DEV_LOGIN=false \
  -e SECRET_KEY=dev \
  -e DATABASE_URL=… \
  -e SESSION_BACKEND=sqlalchemy \
  -e RATELIMIT_STORAGE_BACKEND=sqlalchemy \
  extraction-portal:local
# curl http://localhost:8080/api/health
```

## Migrate then deploy API

```bash
set -a && source deploy/env.deploy.local && set +a

bash deploy/migrate-cloud-run-job.sh
bash deploy/deploy-cloud-run.sh
```

Production env shape (`api/app.py` refuses weak production config):

- `FLASK_ENV=production`, `USE_GCP_SECRETS=true`, `SESSION_COOKIE_SECURE=true`
- `ENABLE_DEV_LOGIN=false`
- `SESSION_COOKIE_NAME=__session`
- `SESSION_BACKEND=sqlalchemy`, `RATELIMIT_STORAGE_BACKEND=sqlalchemy` (default)
- Real `SECRET_KEY` + `FERNET_KEY` via Secret Manager
- `DATABASE_URL` pointing at Cloud SQL

**Redis fallback gate:** if PostgreSQL rate-limit equivalence fails under two-instance tests, set both backends to `redis` and supply `REDIS_URL` (+ VPC Connector if private Memorystore). Never use process-local `memory://` counters.

## Frontend (Firebase)

```bash
bash deploy/build-portal-local.sh
# or: cd portal && npm ci && npm run build
firebase deploy --only hosting
```

Set `PORTAL_URL`, `CORS_ORIGINS`, and both `MS_*_REDIRECT_URI` to the Hosting URL.

## Connection budget

`max instances × gunicorn workers × (DB_POOL_SIZE + DB_MAX_OVERFLOW)` must stay under the Cloud SQL connection limit (leave headroom for migrate Job and scale-out). Defaults: pool 5 + overflow 5, concurrency 8, max instances 10 — tune from load tests.

## Verify after deploy

```bash
curl -sS "$PORTAL_URL/api/health"
# Expect: "status":"ok", "dev_login_enabled":false, "flask_env":"production"
```

Cross-instance checks before first use: OAuth A→B, logout revocation, shared rate limits, Plaid/Graph extract without sticky disk, frontend-only release does not rebuild the API image. Synchronous exports must finish within Firebase’s **60s** Hosting→Cloud Run proxy limit.

## Related docs

- `SECURITY.md` — sessions, secrets, tenancy, CSP, audit logs
- Issue #56 — Firebase + Cloud SQL multi-instance plan
