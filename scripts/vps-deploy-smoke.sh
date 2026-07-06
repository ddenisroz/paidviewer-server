#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-/srv/paidviewer/env/.env}"
COMPOSE_FILE="${COMPOSE_FILE:-deploy/docker/docker-compose.server.yml}"

read_env_var() {
  local key="$1"
  local value
  value="$(grep -E "^[[:space:]]*${key}=" "$ENV_FILE" | tail -n 1 | sed -E "s/^[[:space:]]*${key}=//" || true)"
  value="${value%$'\r'}"
  value="${value#\"}"
  value="${value%\"}"
  value="${value#\'}"
  value="${value%\'}"
  printf '%s' "$value"
}

cd "$ROOT_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE" >&2
  exit 1
fi

IMAGE_TAG="${BOT_SERVICE_IMAGE:-$(read_env_var BOT_SERVICE_IMAGE)}"
IMAGE_TAG="${IMAGE_TAG:-paidviewer-server:local}"

echo "== Paidviewer server deploy smoke =="
echo "Repo: $ROOT_DIR"
echo "Env: $ENV_FILE"
echo "Compose: $COMPOSE_FILE"
echo "Image: $IMAGE_TAG"
echo

echo "== Git revision =="
git log -3 --oneline
echo

echo "== Startup command =="
grep -n "bootstrap_database" bot_service/Dockerfile.prod
echo

echo "== Compose config =="
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config --quiet
echo "Compose config OK"
echo

echo "== Build backend image =="
docker build --no-cache -t "$IMAGE_TAG" -f bot_service/Dockerfile.prod bot_service
echo

echo "== Restart stack =="
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" down
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d
echo

echo "== Containers =="
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps
echo

echo "== bot_service logs =="
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" logs --tail=160 bot_service
echo

echo "== Health =="
for _ in {1..30}; do
  if curl -fsS http://127.0.0.1:8000/health/ready; then
    echo
    echo "Health OK"
    exit 0
  fi
  sleep 2
done

echo "Health check failed after 60 seconds" >&2
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps >&2
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" logs --tail=200 bot_service >&2
exit 1
