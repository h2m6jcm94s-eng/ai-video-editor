#!/usr/bin/env bash
# Start all local Temporal Python workers for ai_video_editor.
# This script delegates to manage-local-workers.py, which correctly tracks
# the Windows python.exe PIDs spawned by `uv run`.
set -euo pipefail

cd "$(dirname "$0")/.."

set -a
source .env
set +a

export AI_PROVIDER="${AI_PROVIDER:-programmatic}"

exec uv run python scripts/manage-local-workers.py
