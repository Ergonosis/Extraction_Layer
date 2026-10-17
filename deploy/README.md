# Deploy tooling

See **[../docs/deploy-gcp.md](../docs/deploy-gcp.md)** for the full GCP production path.

Quick pointers:

- `cloudbuild.yaml` — build/push image
- `migrate-cloud-run-job.sh` — `flask db upgrade`
- `deploy-cloud-run.sh` — Cloud Run service
- `env.deploy.example` — copy to `env.deploy.local` (gitignored)
