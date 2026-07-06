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
SERVICE_PORT="${BOT_SERVICE_PORT:-$(read_env_var BOT_SERVICE_PORT)}"
SERVICE_PORT="${SERVICE_PORT:-8000}"

echo "== Paidviewer server deploy smoke =="
echo "Repo: $ROOT_DIR"
echo "Env: $ENV_FILE"
echo "Compose: $COMPOSE_FILE"
echo "Image: $IMAGE_TAG"
echo "Local health port: $SERVICE_PORT"
echo

echo "== Git revision =="
git log -3 --oneline
git status --short --branch
echo

echo "== Startup command =="
if ! grep -n "bootstrap_database" bot_service/Dockerfile.prod; then
  echo "ERROR: bot_service/Dockerfile.prod does not contain bootstrap_database.py." >&2
  echo "Run 'git pull' in the server repository and retry." >&2
  exit 1
fi
echo

echo "== Compose config =="
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config --quiet
echo "Compose config OK"
echo

echo "== Build backend image =="
docker build --no-cache -t "$IMAGE_TAG" -f bot_service/Dockerfile.prod bot_service
echo

echo "== Built image command =="
IMAGE_CMD="$(docker image inspect "$IMAGE_TAG" --format '{{json .Config.Cmd}}')"
echo "$IMAGE_CMD"
if [[ "$IMAGE_CMD" != *"bootstrap_database.py"* ]]; then
  echo "ERROR: built image command does not include bootstrap_database.py." >&2
  echo "Remove the stale image with 'docker rmi $IMAGE_TAG' and retry the smoke script." >&2
  exit 1
fi
echo

echo "== Restart stack =="
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" down --remove-orphans
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --force-recreate
echo

echo "== Containers =="
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps
echo

echo "== bot_service logs =="
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" logs --tail=160 bot_service
echo

echo "== Health =="
for _ in {1..30}; do
  if curl -fsS "http://127.0.0.1:${SERVICE_PORT}/health/ready"; then
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
