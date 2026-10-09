# Deploy portal to GCP (issue #48)

Same-origin Cloud Run service: **Flask API + built React SPA** in one container so session cookies work with `axios` `baseURL: '/'`.

## What is in git

| Path | Role |
|---|---|
| `Dockerfile` | Multi-stage: `npm run build` → Python image with gunicorn |
| `deploy/cloudbuild.yaml` | Build/push image to Artifact Registry |
| `deploy/migrate-cloud-run-job.sh` | `flask db upgrade` as a Cloud Run Job |
| `deploy/deploy-cloud-run.sh` | Deploy service with prod env + Secret Manager mounts |
| `deploy/build-portal-local.sh` / `.ps1` | Build `portal/dist` without Docker |
| `deploy/env.deploy.example` | Variable names only (copy locally; never commit secrets) |

**Not in repo:** Terraform for Cloud SQL / Memorystore / VPC (provision once; document below). Hardening (Armor, CSP, audit) is issue **#33**.

## One-time GCP setup

1. **Project + APIs:** Cloud Run, Artifact Registry, Cloud Build, Cloud SQL Admin, Secret Manager, VPC Access, Redis (Memorystore).
2. **Artifact Registry** (Docker):
   ```bash
   gcloud artifacts repositories create portal \
     --repository-format=docker --location=us-central1
   ```
3. **Cloud SQL (Postgres)** + **Memorystore (Redis)** on a VPC; **Serverless VPC Access** connector for Cloud Run.
4. **Service account** for Cloud Run with:
   - `roles/secretmanager.secretAccessor`
   - `roles/cloudsql.client`
5. **Secrets** (values never committed):
   ```bash
   # Generate Fernet: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   echo -n '…' | gcloud secrets create SECRET_KEY --data-file=-
   echo -n '…' | gcloud secrets create FERNET_KEY --data-file=-
   echo -n '…' | gcloud secrets create MS_CLIENT_SECRET --data-file=-
   echo -n '…' | gcloud secrets create PLAID_SECRET --data-file=-
   ```
6. **Entra app:** multi-tenant; add production redirect URIs after you know the Cloud Run URL (or custom domain).

## Build image

From repo root (Cloud Shell or CI):

```bash
gcloud builds submit --config deploy/cloudbuild.yaml \
  --substitutions=_REGION=us-central1,_REPO=portal,_IMAGE=extraction-portal
```

Local Docker smoke (optional):

```bash
docker build -t extraction-portal:local .
docker run --rm -p 8080:8080 \
  -e FLASK_ENV=development \
  -e ENABLE_DEV_LOGIN=false \
  -e SECRET_KEY=dev \
  -e DATABASE_URL=… \
  -e REDIS_URL=… \
  extraction-portal:local
# curl http://localhost:8080/api/health
```

## Migrate then deploy

Copy `deploy/env.deploy.example` → `deploy/env.deploy.local` (gitignored pattern: keep local). Fill values, then:

```bash
set -a && source deploy/env.deploy.local && set +a

bash deploy/migrate-cloud-run-job.sh
bash deploy/deploy-cloud-run.sh
```

After first deploy, set `PORTAL_URL`, `CORS_ORIGINS`, and both `MS_*_REDIRECT_URI` to the service URL (or custom domain) and redeploy. Register those URIs in Entra.

## Production env shape (must boot)

App refuses weak production config (`api/app.py`):

- `FLASK_ENV=production`
- `USE_GCP_SECRETS=true`
- `SESSION_COOKIE_SECURE=true`
- `ENABLE_DEV_LOGIN=false`
- Real `SECRET_KEY` + `FERNET_KEY` (via Secret Manager mounts)
- `DATABASE_URL`, `REDIS_URL`, Entra + Plaid as needed

## Portal-only static build

If you ever host the SPA separately (not recommended for cookies unless same site):

```bash
bash deploy/build-portal-local.sh
# or: powershell -File deploy/build-portal-local.ps1
```

Prefer the all-in-one Cloud Run image so `/` and `/api/*` share origin.

## Verify after deploy

```bash
curl -sS "$PORTAL_URL/api/health"
# Expect: "status":"ok", "dev_login_enabled":false, "flask_env":"production"
```

Optional local suite (against Docker Postgres/Redis, not Cloud Run): `scripts/verify_portal_*.py`.

## Related docs

- `SECURITY.md` — sessions, Redis, Secret Manager, tenancy, cost tiers
- Issue #33 — WAF / CSP / audit logs (follow-up)
