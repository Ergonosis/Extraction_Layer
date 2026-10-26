# Deploy tooling

See **[../docs/gcp-launch-runbook.md](../docs/gcp-launch-runbook.md)** for the
frontend-first GCP production path.

Quick pointers:

- `build-portal-local.sh` / `.ps1` — build the Firebase static bundle
- `migrate-cloud-run-job.sh` — future `flask db upgrade` Cloud Run Job
- `env.migrate.example` — future migration Job variables

Backend image build and Cloud Run Service replacement are owned by
`.github/workflows/deploy-backend.yaml` and `infra/portal/cloudrun.yaml`.
