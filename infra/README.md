# Extraction Portal deployment infrastructure

Firebase Hosting serves the SPA independently. GitHub Actions builds the API-only
image and deploys multiple Cloud Run instances with shared PostgreSQL sessions,
rate limits, and business data. The manifest is a Cloud SQL template, not a
disposable SQLite test configuration.

See [the launch runbook](../docs/gcp-launch-runbook.md) for setup and acceptance.

## Configuration

- Project: `auspicious-silo-492102-j6`; region: `us-central1`.
- Hosting site: `ergonosis-extraction-portal`.
- API Service: `extraction-portal`.
- Runtime identity: `extraction-portal-run@auspicious-silo-492102-j6.iam.gserviceaccount.com`.
- GitHub variables: `CLOUD_SQL_INSTANCE`, `DATABASE_URL_SECRET`, `MS_CLIENT_ID`.
  `PLAID_CLIENT_ID` is optional until Plaid is configured.
- Manifest defaults: 1 CPU, 512 MiB, concurrency 8, timeout 60s, min 0 / max 10.

The workflow replaces manifest placeholders only after validating required
configuration and checking Cloud SQL and secret metadata. Do not deploy the
unpatched manifest directly. The preflight never creates resources or enables APIs.

## Release order

1. Authenticate the release identity and validate resource readiness.
2. Build/push the API image and obtain an immutable digest.
3. Run the schema Job with that digest and wait for success.
4. Replace the API Service, wait for Ready, and verify its digest and health.
5. Publish the frontend separately to Firebase Hosting.

The workflow configures browser invocation with `roles/run.invoker` for `allUsers`;
application sessions, CSRF, and tenant checks protect business endpoints.

Backend workflow pushes to `main` or manual dispatch do not publish the SPA.
`.github/workflows/deploy-frontend.yaml` publishes Hosting after checking API readiness.
Frontend-only releases do not change the backend image or revision. Its release
identity additionally needs Firebase Hosting release permissions.

## Resource access

The runtime identity needs Cloud SQL Client and access to the required secret
values. The GitHub WIF release identity needs Artifact Registry write access,
Service/Job deployment and execution permissions, permission to act as the runtime
identity, and permission to configure the browser invocation policy. Metadata
preflight additionally needs `cloudsql.instances.get` and
`secretmanager.versions.get`. These permissions must be provisioned before release;
the workflow does not grant them to itself.

## Verification boundary

Pure Python/mock tests do not establish database atomicity, session revocation
across instances, or Redis equivalence. Those checks and real Hosting smoke tests
remain first-launch gates. No Docker, database, Redis, or GCP tests were requested
for this local implementation.
