#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "== Paidviewer VPS update =="
echo "Repo: $ROOT_DIR"
echo

echo "== Git preflight =="
git status --short --branch
if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: repository has local changes. Commit, stash or remove them before VPS update." >&2
  exit 1
fi

git fetch origin
git pull --ff-only
echo

echo "== Deploy smoke =="
exec bash scripts/vps-deploy-smoke.sh
