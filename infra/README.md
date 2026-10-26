# Extraction Portal deployment infrastructure

The backend is deployed by GitHub Actions. The current manifest is a disposable
test configuration: SQLite is local to one Cloud Run instance and Redis is
disabled. It is intended for fast end-to-end testing, not retained data.

## One-time Console resources

Use project `auspicious-silo-492102-j6` and region `us-central1`.

1. Create Docker Artifact Registry repository `portal`. Leave tag immutability
   disabled because the workflow publishes both the Git SHA and `latest` tags.
2. Create service account
   `extraction-portal-run@auspicious-silo-492102-j6.iam.gserviceaccount.com`.
3. Grant that service account Secret Accessor on `SECRET_KEY` and `FERNET_KEY`.
4. Create private Cloud Run Service `extraction-portal` from the placeholder
   image `us-docker.pkg.dev/cloudrun/container/hello`:
   - require authentication;
   - ingress `all`;
   - runtime service account `extraction-portal-run`;
   - 1 CPU, 512 MiB, concurrency 8, timeout 60 seconds;
   - minimum 0 and maximum 1 instance;
   - request-based CPU allocation.

The first GitHub deployment replaces the placeholder revision and makes
`infra/portal/cloudrun.yaml` the source of truth for Service configuration.
Cloud Run IAM policy is separate and remains private.

## One-time GitHub WIF bindings

The existing provider accepts repositories owned by `Ergonosis`, so only
resource-level bindings are needed for this repository.

```bash
export GCP_PROJECT_ID=auspicious-silo-492102-j6
export GCP_REGION=us-central1
export PROJECT_NUMBER=111021901996
export WIF_POOL=bot-identity-pool
export GITHUB_REPOSITORY=Ergonosis/Extraction_Layer
export RUNTIME_SA=extraction-portal-run@${GCP_PROJECT_ID}.iam.gserviceaccount.com
export WIF_PRINCIPAL="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WIF_POOL}/attribute.repository/${GITHUB_REPOSITORY}"

gcloud artifacts repositories add-iam-policy-binding portal \
  --project="${GCP_PROJECT_ID}" \
  --location="${GCP_REGION}" \
  --member="${WIF_PRINCIPAL}" \
  --role=roles/artifactregistry.writer

gcloud run services add-iam-policy-binding extraction-portal \
  --project="${GCP_PROJECT_ID}" \
  --region="${GCP_REGION}" \
  --member="${WIF_PRINCIPAL}" \
  --role=roles/run.developer

gcloud iam service-accounts add-iam-policy-binding "${RUNTIME_SA}" \
  --project="${GCP_PROJECT_ID}" \
  --member="${WIF_PRINCIPAL}" \
  --role=roles/iam.serviceAccountUser
```

No GCP JSON key or GitHub secret is required.

## Deploy and verify

Run **Deploy Extraction Backend** from GitHub Actions for the first deployment.
Backend-related pushes to `main` deploy automatically after that.

The workflow runs tests, pushes Git-SHA and `latest` image tags, deploys the
immutable digest, and verifies the Ready revision and deployed digest.

The Service is private during bootstrap. Verify it from an authenticated shell:

```bash
export GCP_PROJECT_ID=auspicious-silo-492102-j6
export GCP_REGION=us-central1
export SERVICE_NAME=extraction-portal
export SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" \
  --project="${GCP_PROJECT_ID}" \
  --region="${GCP_REGION}" \
  --format='value(status.url)')"

curl --fail --show-error --silent \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "${SERVICE_URL}/api/health"
```

Expected fields are `status: ok`, `flask_env: production`, and
`dev_login_enabled: false`.

## Rollback

Use Cloud Run Console to move traffic back to the previous Ready revision. Each
revision references an immutable digest. A selected Git ref can also be
redeployed with `workflow_dispatch`.

## Disposable test limitation

`AUTO_MIGRATE_ON_START=true` makes the Flask app factory run Alembic against
`sqlite:////tmp/portal-test.db`. Gunicorn workers serialize this step with a
shared `/tmp` file lock; after the first upgrade, later workers see an Alembic
no-op. The local database disappears when Cloud Run replaces or stops the
instance, including normal scale-to-zero and deployments. Users must then sign
in and reconnect Plaid or Microsoft Graph.

`REDIS_URL` is empty, so Flask uses signed client-side cookies and the rate
limiter uses process memory. `maxScale=1` prevents separate instances from
creating divergent databases, but the two Gunicorn workers can still maintain
independent rate-limit counters. This is acceptable only for low-volume tests.

After the private health check succeeds, an operator may explicitly make the
Service callable by Firebase and publish the `/api/**` rewrite. Do not store
data that must survive a restart.
