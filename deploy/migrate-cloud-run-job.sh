#!/usr/bin/env bash
# Run Alembic migrations against Cloud SQL via a one-shot Cloud Run Job.
# Uses the same image as the API. Safe to re-run (Alembic tracks revisions).
#
# Required env: GCP_PROJECT_ID, REGION, CLOUD_SQL_INSTANCE, IMAGE (digest), and either
#               DATABASE_URL_SECRET (preferred) or DATABASE_URL
# Optional: JOB_NAME (default extraction-portal-migrate), VPC_CONNECTOR,
#           SERVICE_ACCOUNT, and Secret Manager ids.
# See deploy/env.migrate.example. The backend workflow executes this Job before publishing a revision.

set -euo pipefail

: "${GCP_PROJECT_ID:?set GCP_PROJECT_ID}"
: "${REGION:?set REGION}"
: "${IMAGE:?set IMAGE to the API image digest}"
: "${CLOUD_SQL_INSTANCE:?set CLOUD_SQL_INSTANCE}"
if [[ ! "$IMAGE" =~ @sha256:[a-f0-9]{64}$ ]]; then
  echo "IMAGE must reference an immutable sha256 digest" >&2
  exit 1
fi
JOB_NAME="${JOB_NAME:-extraction-portal-migrate}"
SECRET_KEY_SECRET="${SECRET_KEY_SECRET:-SECRET_KEY}"
FERNET_KEY_SECRET="${FERNET_KEY_SECRET:-FERNET_KEY}"
DATABASE_URL_SECRET="${DATABASE_URL_SECRET:-}"

if [[ -z "${DATABASE_URL_SECRET}" && -z "${DATABASE_URL:-}" ]]; then
  echo "set DATABASE_URL_SECRET (preferred) or DATABASE_URL" >&2
  exit 1
fi

ENV_JOINED="FLASK_APP=src.api.app:create_app,FLASK_ENV=production,USE_GCP_SECRETS=true,GCP_PROJECT_ID=${GCP_PROJECT_ID},ENABLE_DEV_LOGIN=false,SESSION_COOKIE_SECURE=true,SESSION_COOKIE_NAME=__session,SESSION_BACKEND=sqlalchemy,RATELIMIT_STORAGE_BACKEND=sqlalchemy"
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
