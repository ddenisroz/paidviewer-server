#!/usr/bin/env bash
set -Eeuo pipefail

ENV_FILE="${ENV_FILE:-/srv/paidviewer/env/.env}"
DATA_DIR="${PAIDVIEWER_DATA_DIR:-/srv/paidviewer}"

echo "== Paidviewer server bootstrap =="
echo "Data dir: $DATA_DIR"
echo "Env file: $ENV_FILE"
echo

mkdir -p "$DATA_DIR"/{env,uploads,logs,backups,postgres,redis,bot-data}

if [[ ! -f "$ENV_FILE" ]]; then
  cp deploy/docker/.env.example "$ENV_FILE"
  echo "Created $ENV_FILE from deploy/docker/.env.example"
  echo "Edit it before starting the server:"
  echo "  nano $ENV_FILE"
  exit 1
fi

echo "Env file already exists."
echo
echo "Next commands:"
echo "  bash scripts/vps-deploy-smoke.sh"
echo
echo "For IP-only Vercel setup, follow docs/IP_ONLY_VERCEL_GUIDE.md"
