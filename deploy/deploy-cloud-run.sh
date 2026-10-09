#!/usr/bin/env bash
# Deploy the portal API (+ SPA) image to Cloud Run.
# Prerequisites: gcloud auth, Artifact Registry image already built, secrets created,
# Cloud SQL + Memorystore reachable (VPC connector), service account with Secret Manager access.
#
# Required env:
#   GCP_PROJECT_ID, REGION, SERVICE_NAME, VPC_CONNECTOR
#   CLOUD_SQL_INSTANCE   (project:region:instance)
#   DATABASE_URL         (Cloud SQL Postgres URL; prefer secret or private IP)
#   REDIS_URL            (Memorystore URL)
#   PORTAL_URL           (https://… Cloud Run URL or custom domain)
#   MS_CLIENT_ID, MS_REDIRECT_URI, MS_GRAPH_REDIRECT_URI
#   CORS_ORIGINS         (usually same as PORTAL_URL)
#
# Optional:
#   IMAGE                (full image URI; default Artifact Registry latest)
#   AR_REPO, IMAGE_NAME  (defaults: portal / extraction-portal)
#   SERVICE_ACCOUNT      (runtime SA email)
#   MS_TENANT_ALLOWLIST, PLAID_ENV, PLAID_CLIENT_ID
#   SECRET_KEY_SECRET, FERNET_KEY_SECRET, MS_CLIENT_SECRET_SECRET, PLAID_SECRET_SECRET
#     (Secret Manager secret *ids*; default to SECRET_KEY, FERNET_KEY, …)

set -euo pipefail

: "${GCP_PROJECT_ID:?set GCP_PROJECT_ID}"
: "${REGION:?set REGION (e.g. us-central1)}"
: "${SERVICE_NAME:?set SERVICE_NAME (e.g. extraction-portal)}"
: "${DATABASE_URL:?set DATABASE_URL}"
: "${REDIS_URL:?set REDIS_URL}"
: "${PORTAL_URL:?set PORTAL_URL}"
: "${MS_CLIENT_ID:?set MS_CLIENT_ID}"
: "${MS_REDIRECT_URI:?set MS_REDIRECT_URI}"
: "${MS_GRAPH_REDIRECT_URI:?set MS_GRAPH_REDIRECT_URI}"

AR_REPO="${AR_REPO:-portal}"
IMAGE_NAME="${IMAGE_NAME:-extraction-portal}"
IMAGE="${IMAGE:-${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${AR_REPO}/${IMAGE_NAME}:latest}"
CORS_ORIGINS="${CORS_ORIGINS:-${PORTAL_URL}}"
PLAID_ENV="${PLAID_ENV:-sandbox}"
SECRET_KEY_SECRET="${SECRET_KEY_SECRET:-SECRET_KEY}"
FERNET_KEY_SECRET="${FERNET_KEY_SECRET:-FERNET_KEY}"
MS_CLIENT_SECRET_SECRET="${MS_CLIENT_SECRET_SECRET:-MS_CLIENT_SECRET}"
PLAID_SECRET_SECRET="${PLAID_SECRET_SECRET:-PLAID_SECRET}"

ENV_VARS=(
  "FLASK_ENV=production"
  "USE_GCP_SECRETS=true"
  "GCP_PROJECT_ID=${GCP_PROJECT_ID}"
  "ENABLE_DEV_LOGIN=false"
  "SESSION_COOKIE_SECURE=true"
  "PORTAL_STATIC_DIR=/app/portal_dist"
  "DATABASE_URL=${DATABASE_URL}"
  "REDIS_URL=${REDIS_URL}"
  "PORTAL_URL=${PORTAL_URL}"
  "PORTAL_POST_LOGIN_PATH=/connections"
  "CORS_ORIGINS=${CORS_ORIGINS}"
  "MS_CLIENT_ID=${MS_CLIENT_ID}"
  "MS_REDIRECT_URI=${MS_REDIRECT_URI}"
  "MS_GRAPH_REDIRECT_URI=${MS_GRAPH_REDIRECT_URI}"
  "MS_AUTHORITY=https://login.microsoftonline.com/organizations"
  "PLAID_ENV=${PLAID_ENV}"
)

if [[ -n "${MS_TENANT_ALLOWLIST:-}" ]]; then
  ENV_VARS+=("MS_TENANT_ALLOWLIST=${MS_TENANT_ALLOWLIST}")
fi
if [[ -n "${PLAID_CLIENT_ID:-}" ]]; then
  ENV_VARS+=("PLAID_CLIENT_ID=${PLAID_CLIENT_ID}")
fi

# Join ENV_VARS with commas for gcloud
IFS=','; ENV_JOINED="${ENV_VARS[*]}"; unset IFS

# gcloud format: ENV_VAR=SECRET_ID:VERSION
SECRETS_JOINED="SECRET_KEY=${SECRET_KEY_SECRET}:latest,FERNET_KEY=${FERNET_KEY_SECRET}:latest,MS_CLIENT_SECRET=${MS_CLIENT_SECRET_SECRET}:latest"
if [[ -n "${PLAID_CLIENT_ID:-}" ]]; then
  SECRETS_JOINED="${SECRETS_JOINED},PLAID_SECRET=${PLAID_SECRET_SECRET}:latest"
fi

ARGS=(
  run deploy "${SERVICE_NAME}"
  --project="${GCP_PROJECT_ID}"
  --region="${REGION}"
  --image="${IMAGE}"
  --platform=managed
  --allow-unauthenticated
  --port=8080
  --cpu=1
  --memory=512Mi
  --min-instances=0
  --max-instances=10
  --set-env-vars="${ENV_JOINED}"
  --set-secrets="${SECRETS_JOINED}"
)

if [[ -n "${SERVICE_ACCOUNT:-}" ]]; then
  ARGS+=(--service-account="${SERVICE_ACCOUNT}")
fi
if [[ -n "${VPC_CONNECTOR:-}" ]]; then
  ARGS+=(--vpc-connector="${VPC_CONNECTOR}" --vpc-egress=private-ranges-only)
fi
if [[ -n "${CLOUD_SQL_INSTANCE:-}" ]]; then
  ARGS+=(--add-cloudsql-instances="${CLOUD_SQL_INSTANCE}")
fi

echo "Deploying ${IMAGE} -> Cloud Run service ${SERVICE_NAME} (${REGION})"
gcloud "${ARGS[@]}"

URL="$(gcloud run services describe "${SERVICE_NAME}" --project="${GCP_PROJECT_ID}" --region="${REGION}" --format='value(status.url)')"
echo "Deployed: ${URL}"
echo "Health:   ${URL}/api/health"
echo "Remember: PORTAL_URL / MS_* redirect URIs / CORS_ORIGINS should match this URL (or your custom domain)."
