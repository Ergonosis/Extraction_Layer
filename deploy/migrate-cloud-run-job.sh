#!/usr/bin/env bash
# Run Alembic migrations against Cloud SQL via a one-shot Cloud Run Job.
# Uses the same image as the API. Safe to re-run (Alembic tracks revisions).
#
# Required env: GCP_PROJECT_ID, REGION, IMAGE (or AR_REPO defaults), and either
#               DATABASE_URL_SECRET (preferred) or DATABASE_URL
# Optional: JOB_NAME (default extraction-portal-migrate), VPC_CONNECTOR,
#           CLOUD_SQL_INSTANCE, SERVICE_ACCOUNT, and Secret Manager ids.
# See deploy/env.migrate.example. This Job is intentionally outside the current
# backend deployment workflow until Cloud SQL is provisioned.

set -euo pipefail

: "${GCP_PROJECT_ID:?set GCP_PROJECT_ID}"
: "${REGION:?set REGION}"
AR_REPO="${AR_REPO:-portal}"
IMAGE_NAME="${IMAGE_NAME:-extraction-portal}"
IMAGE="${IMAGE:-${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${AR_REPO}/${IMAGE_NAME}:latest}"
JOB_NAME="${JOB_NAME:-extraction-portal-migrate}"
SECRET_KEY_SECRET="${SECRET_KEY_SECRET:-SECRET_KEY}"
FERNET_KEY_SECRET="${FERNET_KEY_SECRET:-FERNET_KEY}"
DATABASE_URL_SECRET="${DATABASE_URL_SECRET:-}"

if [[ -z "${DATABASE_URL_SECRET}" && -z "${DATABASE_URL:-}" ]]; then
  echo "set DATABASE_URL_SECRET (preferred) or DATABASE_URL" >&2
  exit 1
fi

ENV_JOINED="FLASK_APP=src.api.app:create_app,FLASK_ENV=production,USE_GCP_SECRETS=true,GCP_PROJECT_ID=${GCP_PROJECT_ID},ENABLE_DEV_LOGIN=false,SESSION_COOKIE_SECURE=true"
SECRETS_JOINED="SECRET_KEY=${SECRET_KEY_SECRET}:latest,FERNET_KEY=${FERNET_KEY_SECRET}:latest"
if [[ -n "${DATABASE_URL_SECRET}" ]]; then
  SECRETS_JOINED="${SECRETS_JOINED},DATABASE_URL=${DATABASE_URL_SECRET}:latest"
else
  ENV_JOINED="${ENV_JOINED},DATABASE_URL=${DATABASE_URL}"
fi

ARGS=(
  run jobs deploy "${JOB_NAME}"
  --project="${GCP_PROJECT_ID}"
  --region="${REGION}"
  --image="${IMAGE}"
  --command=flask
  --args=db,upgrade
  --set-env-vars="${ENV_JOINED}"
  --set-secrets="${SECRETS_JOINED}"
  --max-retries=1
  --task-timeout=10m
  --cpu=1
  --memory=512Mi
)

if [[ -n "${SERVICE_ACCOUNT:-}" ]]; then
  ARGS+=(--service-account="${SERVICE_ACCOUNT}")
fi
if [[ -n "${VPC_CONNECTOR:-}" ]]; then
  ARGS+=(--vpc-connector="${VPC_CONNECTOR}" --vpc-egress=private-ranges-only)
fi
if [[ -n "${CLOUD_SQL_INSTANCE:-}" ]]; then
  ARGS+=(--set-cloudsql-instances="${CLOUD_SQL_INSTANCE}")
fi

echo "Upserting Cloud Run Job ${JOB_NAME}"
gcloud "${ARGS[@]}"

echo "Executing migration job…"
gcloud run jobs execute "${JOB_NAME}" \
  --project="${GCP_PROJECT_ID}" \
  --region="${REGION}" \
  --wait

echo "Migrations finished."
