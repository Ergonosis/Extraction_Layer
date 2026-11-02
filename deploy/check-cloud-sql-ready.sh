#!/usr/bin/env bash
# Metadata-only preflight. Never enables APIs, creates resources, or reads secret values.
set -euo pipefail

: "${GCP_PROJECT_ID:?set GCP_PROJECT_ID}"
: "${GCP_REGION:?set GCP_REGION}"
: "${CLOUD_SQL_INSTANCE:?set CLOUD_SQL_INSTANCE}"

IFS=: read -r SQL_PROJECT SQL_REGION SQL_NAME EXTRA <<< "$CLOUD_SQL_INSTANCE"
if [[ "$SQL_PROJECT" != "$GCP_PROJECT_ID" || "$SQL_REGION" != "$GCP_REGION" || -n "${EXTRA:-}" || ! "$SQL_NAME" =~ ^[a-z][a-z0-9-]+$ ]]; then
  echo "CLOUD_SQL_INSTANCE must be project:region:instance in the configured project and region" >&2
  exit 1
fi
STATE=$(gcloud sql instances describe "$SQL_NAME" --project="$GCP_PROJECT_ID" --quiet --format='value(state)')
if [[ "$STATE" != RUNNABLE ]]; then
  echo "Cloud SQL is not RUNNABLE; refusing to build or deploy" >&2
  exit 1
fi
SECRETS=(
  EXTRACTION_PORTAL_DATABASE_URL EXTRACTION_PORTAL_FLASK_SECRET_KEY
  EXTRACTION_PORTAL_FERNET_KEY MSGRAPH_CLIENT_SECRET MSGRAPH_CLIENT_ID
  PLAID_SECRET PLAID_CLIENT_ID PLAID_ENV
)
for SECRET_ID in "${SECRETS[@]}"; do
  if [[ ! "$SECRET_ID" =~ ^[a-zA-Z0-9_-]+$ ]]; then
    echo "Invalid secret id" >&2
    exit 1
  fi
  STATE=$(gcloud secrets versions describe latest --secret="$SECRET_ID" --project="$GCP_PROJECT_ID" --quiet --format='value(state)')
  if [[ "$STATE" != ENABLED ]]; then
    echo "Required secret version is not ENABLED: $SECRET_ID" >&2
    exit 1
  fi
done
