#!/usr/bin/env bash
# Clean up merged and stale branches locally and remotely.
# Run this after PRs merge to keep the repo tidy.
#
# Usage: pnpm branch:clean
# Or directly: bash scripts/clean-branches.sh

set -euo pipefail

MAIN_BRANCH="main"
REMOTE="origin"

echo "=== Pruning remote tracking refs ==="
git remote prune "$REMOTE"

echo "=== Deleting local branches already merged into $MAIN_BRANCH ==="
merged_locals=$(git branch --merged "$MAIN_BRANCH" --format='%(refname:short)' | grep -v "^${MAIN_BRANCH}$" || true)
if [ -n "$merged_locals" ]; then
  echo "$merged_locals" | xargs -r git branch -d
else
  echo "No merged local branches to delete."
fi

echo "=== Deleting remote branches already merged into $MAIN_BRANCH ==="
merged_remotes=$(git branch -r --merged "$MAIN_BRANCH" --format='%(refname:short)' | grep "^${REMOTE}/" | grep -v "^${REMOTE}/${MAIN_BRANCH}$" | grep -v "^${REMOTE}/HEAD" || true)
if [ -n "$merged_remotes" ]; then
  echo "$merged_remotes" | sed "s|^${REMOTE}/||" | xargs -r git push "$REMOTE" --delete
else
  echo "No merged remote branches to delete."
fi

echo "=== Stale branch check (>30 days since last commit) ==="
stale_locals=$(git for-each-ref --sort='committerdate:iso8601' --format='%(refname:short) %(committerdate:short)' refs/heads/ | awk -v date="$(date -d '30 days ago' +%Y-%m-%d 2>/dev/null || date -v-30d +%Y-%m-%d)" '$2 < date {print $1}' | grep -v "^${MAIN_BRANCH}$" || true)
if [ -n "$stale_locals" ]; then
  echo "The following local branches are older than 30 days:"
  echo "$stale_locals"
  echo "Review and delete manually if no longer needed."
else
  echo "No stale local branches found."
fi

echo "=== Done ==="
