#!/usr/bin/env bash
# Local production build of the React portal (output: portal/dist).
# Frontend-only build for Firebase Hosting; the API image does not include the SPA.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}/portal"
bun install --frozen-lockfile
bun run build
echo "Built ${ROOT}/portal/dist"
