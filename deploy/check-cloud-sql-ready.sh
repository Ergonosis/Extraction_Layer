#!/usr/bin/env bash
# Metadata-only preflight. Never enables APIs, creates resources, or reads secret values.
set -euo pipefail

: "${GCP_PROJECT_ID:?set GCP_PROJECT_ID}"
: "${GCP_REGION:?set GCP_REGION}"
: "${CLOUD_SQL_INSTANCE:?set CLOUD_SQL_INSTANCE}"
: "${DATABASE_URL_SECRET:?set DATABASE_URL_SECRET}"
: "${MS_CLIENT_ID:?set MS_CLIENT_ID}"

IFS=: read -r SQL_PROJECT SQL_REGION SQL_NAME EXTRA <<< "$CLOUD_SQL_INSTANCE"
if [[ "$SQL_PROJECT" != "$GCP_PROJECT_ID" || "$SQL_REGION" != "$GCP_REGION" || -n "${EXTRA:-}" || ! "$SQL_NAME" =~ ^[a-z][a-z0-9-]+$ ]]; then
  echo "CLOUD_SQL_INSTANCE must be project:region:instance in the configured project and region" >&2
  exit 1
fi
if [[ ! "$DATABASE_URL_SECRET" =~ ^[a-zA-Z0-9_-]+$ || ! "$MS_CLIENT_ID" =~ ^[a-zA-Z0-9-]+$ || ! "${PLAID_CLIENT_ID:-}" =~ ^[a-zA-Z0-9_-]*$ ]]; then
  echo "Invalid secret id or client id" >&2
  exit 1
fi

STATE=$(gcloud sql instances describe "$SQL_NAME" --project="$GCP_PROJECT_ID" --quiet --format='value(state)')
if [[ "$STATE" != RUNNABLE ]]; then
  echo "Cloud SQL is not RUNNABLE; refusing to build or deploy" >&2
  exit 1
fi
SECRETS=("$DATABASE_URL_SECRET" SECRET_KEY FERNET_KEY MS_CLIENT_SECRET)
if [[ -n "${PLAID_CLIENT_ID:-}" ]]; then
  SECRETS+=(PLAID_SECRET)
fi
for SECRET_ID in "${SECRETS[@]}"; do
  STATE=$(gcloud secrets versions describe latest --secret="$SECRET_ID" --project="$GCP_PROJECT_ID" --quiet --format='value(state)')
  if [[ "$STATE" != ENABLED ]]; then
    echo "Required secret version is not ENABLED: $SECRET_ID" >&2
    exit 1
  fi
done
