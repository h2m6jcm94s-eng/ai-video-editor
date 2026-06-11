#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -z "${PEXELS_API_KEY:-}" ]; then
  echo "Error: PEXELS_API_KEY is not set"
  exit 1
fi

if [ -z "${FREESOUND_API_TOKEN:-}" ]; then
  echo "Error: FREESOUND_API_TOKEN is not set"
  exit 1
fi

echo "==> Selecting fixtures..."
node scripts/select-fixtures.mjs

echo "==> Downloading fixtures..."
node scripts/download-from-manifest.mjs

echo "==> Done."
