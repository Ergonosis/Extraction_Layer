# Deploy tooling

See [the GCP launch runbook](../docs/gcp-launch-runbook.md).

- `check-cloud-sql-ready.sh`: validate configuration and Cloud SQL/secret metadata
  before building; never enables APIs or reads secret values.
- `migrate-cloud-run-job.sh`: run `flask db upgrade` using the API image digest.
- `env.migrate.example`: manual schema Job variables; supply the actual digest.
- `build-portal-local.sh` / `.ps1`: explicitly build the Firebase static bundle
  with bun. These are not invoked by backend image builds.

The backend workflow owns schema-before-Service deployment. Frontend releases
are separate; neither local builds nor cloud deployment run merely by editing files.
