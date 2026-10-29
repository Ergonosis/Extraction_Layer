# Deploy tooling

See **[../docs/deploy-gcp.md](../docs/deploy-gcp.md)** for Firebase Hosting + API-only Cloud Run + Cloud SQL.

Quick pointers:

- `cloudbuild.yaml` — build/push **API-only** image
- `migrate-cloud-run-job.sh` — `flask db upgrade` (run before API traffic)
- `deploy-cloud-run.sh` — Cloud Run API service (`__session`, sqlalchemy backends by default)
- `build-portal-local.sh` / `.ps1` — build `portal/dist` for Firebase Hosting
- `env.deploy.example` — copy to `env.deploy.local` (gitignored)
- Root `firebase.json` — Hosting `/api/**` rewrite to Cloud Run
