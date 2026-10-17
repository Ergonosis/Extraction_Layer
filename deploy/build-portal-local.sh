#!/usr/bin/env bash
# Local production build of the React portal (output: portal/dist).
# The Docker image build also runs this; use this script to inspect dist/ without Docker.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}/portal"
npm ci
npm run build
echo "Built ${ROOT}/portal/dist"
