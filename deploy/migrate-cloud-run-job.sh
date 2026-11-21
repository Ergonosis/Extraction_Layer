#!/usr/bin/env bash
# Run Alembic migrations against Cloud SQL via a one-shot Cloud Run Job.
# Uses the same image as the API. Safe to re-run (Alembic tracks revisions).
#
# Required env: GCP_PROJECT_ID, REGION, CLOUD_SQL_INSTANCE, IMAGE (digest), and either
# Secrets use their fixed Portal names in both environment variables and Secret Manager.
# Required: SERVICE_ACCOUNT. Optional: JOB_NAME (default extraction-portal-migrate).
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
: "${SERVICE_ACCOUNT:?set SERVICE_ACCOUNT}"
export JOB_NAME IMAGE CLOUD_SQL_INSTANCE SERVICE_ACCOUNT GCP_PROJECT_ID
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
JOB_FILE=$(mktemp)
trap 'unlink "$JOB_FILE"' EXIT
python "$SCRIPT_DIR/render-sql-job.py" > "$JOB_FILE"

gcloud run jobs replace "$JOB_FILE" --project="$GCP_PROJECT_ID" --region="$REGION" --quiet

gcloud run jobs execute "$JOB_NAME" --project="$GCP_PROJECT_ID" --region="$REGION" --wait --quiet
