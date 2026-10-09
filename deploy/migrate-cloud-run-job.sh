#!/usr/bin/env bash
# Run Alembic migrations against Cloud SQL via a one-shot Cloud Run Job.
# Uses the same image as the API. Safe to re-run (Alembic tracks revisions).
#
# Required env: GCP_PROJECT_ID, REGION, DATABASE_URL, IMAGE (or AR_REPO defaults)
# Optional: JOB_NAME (default extraction-portal-migrate), VPC_CONNECTOR, CLOUD_SQL_INSTANCE,
#           SERVICE_ACCOUNT, USE_GCP_SECRETS / secrets for DB URL if preferred later

set -euo pipefail

: "${GCP_PROJECT_ID:?set GCP_PROJECT_ID}"
: "${REGION:?set REGION}"
: "${DATABASE_URL:?set DATABASE_URL}"

AR_REPO="${AR_REPO:-portal}"
IMAGE_NAME="${IMAGE_NAME:-extraction-portal}"
IMAGE="${IMAGE:-${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${AR_REPO}/${IMAGE_NAME}:latest}"
JOB_NAME="${JOB_NAME:-extraction-portal-migrate}"

ARGS=(
  run jobs deploy "${JOB_NAME}"
  --project="${GCP_PROJECT_ID}"
  --region="${REGION}"
  --image="${IMAGE}"
  --command=flask
  --args=db,upgrade
  --set-env-vars="FLASK_APP=api.app:create_app,FLASK_ENV=production,DATABASE_URL=${DATABASE_URL},ENABLE_DEV_LOGIN=false"
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
