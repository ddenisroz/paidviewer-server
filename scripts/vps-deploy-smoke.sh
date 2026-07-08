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

is_placeholder_value() {
  local value="$1"
  [[ -z "$value" || "$value" == *"change-me"* || "$value" == *"CHANGE_ME"* || "$value" == *"YOUR_"* || "$value" == *"<"* || "$value" == *">"* ]]
}

require_env_value() {
  local key="$1"
  local value
  value="$(read_env_var "$key")"
  if is_placeholder_value "$value"; then
    echo "ERROR: $key is empty or still contains a placeholder in $ENV_FILE." >&2
    return 1
  fi
}

require_https_url() {
  local key="$1"
  local value
  value="$(read_env_var "$key")"
  require_env_value "$key"
  if [[ "$value" != https://* ]]; then
    echo "ERROR: $key must start with https:// for the Vercel production setup. Current value: $value" >&2
    return 1
  fi
}

warn_if_placeholder() {
  local key="$1"
  local value
  value="$(read_env_var "$key")"
  if [[ -n "$value" ]] && is_placeholder_value "$value"; then
    echo "WARN: $key still looks like a placeholder. Leave it empty until you configure that integration." >&2
  fi
}

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "ERROR: required command is missing: $command_name" >&2
    return 1
  fi
}

inspect_image_if_exists() {
  local image_tag="$1"
  if docker image inspect "$image_tag" >/dev/null 2>&1; then
    docker image inspect "$image_tag" \
      --format 'image={{.RepoTags}} id={{.Id}} created={{.Created}} cmd={{json .Config.Cmd}}'
  else
    echo "image=$image_tag not found locally"
  fi
}

inspect_container_if_exists() {
  local container_name="$1"
  if docker container inspect "$container_name" >/dev/null 2>&1; then
    docker container inspect "$container_name" \
      --format 'container={{.Name}} image={{.Config.Image}} status={{.State.Status}} restarting={{.State.Restarting}} exit={{.State.ExitCode}} cmd={{json .Config.Cmd}}'
  else
    echo "container=$container_name not found"
  fi
}

show_failure_context() {
  echo "== Failure context ==" >&2
  inspect_image_if_exists "$IMAGE_TAG" >&2
  inspect_container_if_exists paidviewer_bot_service >&2
  docker port paidviewer_bot_service 8000/tcp >&2 || true
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps >&2 || true
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" logs --tail=240 bot_service >&2 || true
}

run_privileged() {
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

prepare_runtime_dirs() {
  local data_dir
  data_dir="${PAIDVIEWER_DATA_DIR:-$(read_env_var PAIDVIEWER_DATA_DIR)}"
  data_dir="${data_dir:-/srv/paidviewer}"

  run_privileged mkdir -p \
    "$data_dir/env" \
    "$data_dir/uploads" \
    "$data_dir/logs" \
    "$data_dir/backups" \
    "$data_dir/postgres" \
    "$data_dir/redis" \
    "$data_dir/bot-data"

  # bot_service runs as appuser uid 1000 in Dockerfile.prod.
  # These bind mounts must be writable by that uid even when the VPS deploy is run as root.
  run_privileged chown -R 1000:1000 \
    "$data_dir/uploads" \
    "$data_dir/logs" \
    "$data_dir/backups" \
    "$data_dir/bot-data"
}

run_backend_image_preflight() {
  local postgres_user postgres_password postgres_db redis_password
  postgres_user="$(read_env_var POSTGRES_USER)"
  postgres_password="$(read_env_var POSTGRES_PASSWORD)"
  postgres_db="$(read_env_var POSTGRES_DB)"
  redis_password="$(read_env_var REDIS_PASSWORD)"

  docker run --rm -i \
    --env-file "$ENV_FILE" \
    --env ENVIRONMENT=production \
    --env DEBUG=false \
    --env "DATABASE_URL=postgresql://${postgres_user}:${postgres_password}@postgres:5432/${postgres_db}" \
    --env "REDIS_URL=redis://:${redis_password}@redis:6379/0" \
    --env LOG_FILE=/app/logs/preflight.log \
    --entrypoint python \
    "$IMAGE_TAG" - <<'PY'
from pathlib import Path

from scripts import bootstrap_database

if bootstrap_database.APP_ROOT != Path("/app"):
    raise SystemExit(f"Unexpected bootstrap APP_ROOT: {bootstrap_database.APP_ROOT}")

from core.structured_logging import _resolve_log_file_path

resolved_log_file = _resolve_log_file_path("logs/bot_service.log")
if resolved_log_file != Path("/app/logs/bot_service.log"):
    raise SystemExit(f"Unexpected log file path: {resolved_log_file}")

from main import create_app

app = create_app()
paths = {route.path for route in app.routes}
if "/health/ready" not in paths:
    raise SystemExit("/health/ready route is missing")

print("Backend image preflight OK")
PY
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

echo "== Tooling preflight =="
require_command git
require_command docker
require_command curl
if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: Docker Compose plugin is unavailable. Install Docker with the compose plugin and retry." >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker daemon is not reachable. Start Docker and retry." >&2
  exit 1
fi
echo "Docker: $(docker --version)"
echo "Compose: $(docker compose version)"
echo "Tooling preflight OK"
echo

echo "== Env preflight =="
require_env_value POSTGRES_USER
require_env_value POSTGRES_PASSWORD
require_env_value POSTGRES_DB
require_env_value REDIS_PASSWORD
require_env_value BOT_SERVICE_IMAGE
require_env_value SECRET_KEY
require_env_value TOKEN_ENCRYPTION_KEY
require_https_url BACKEND_URL
require_https_url FRONTEND_URL
require_env_value CORS_ORIGINS

TOKEN_ENCRYPTION_KEY_VALUE="$(read_env_var TOKEN_ENCRYPTION_KEY)"
if [[ ! "$TOKEN_ENCRYPTION_KEY_VALUE" =~ ^[A-Za-z0-9_-]{43}=$ ]]; then
  echo "ERROR: TOKEN_ENCRYPTION_KEY must be a Fernet key, not a random password." >&2
  echo "Generate it with:" >&2
  echo "docker run --rm python:3.12-slim sh -lc \"pip install -q cryptography && python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'\"" >&2
  exit 1
fi

if [[ "$(read_env_var CORS_ORIGINS)" != *"$(read_env_var FRONTEND_URL)"* ]]; then
  echo "WARN: CORS_ORIGINS does not contain FRONTEND_URL. Browser requests from Vercel may fail CORS." >&2
fi

for optional_key in \
  TWITCH_CLIENT_ID TWITCH_CLIENT_SECRET TWITCH_REDIRECT_URI TWITCH_BOT_REDIRECT_URI \
  VK_CLIENT_ID VK_CLIENT_SECRET VK_REDIRECT_URI VK_BOT_REDIRECT_URI \
  DONATIONALERTS_CLIENT_ID DONATIONALERTS_CLIENT_SECRET DONATIONALERTS_REDIRECT_URI DONATIONALERTS_WEBHOOK_SECRET; do
  warn_if_placeholder "$optional_key"
done
echo "Env preflight OK"
echo

echo "== Runtime directories =="
prepare_runtime_dirs
echo "Runtime directories OK"
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

echo "== Existing backend image =="
inspect_image_if_exists "$IMAGE_TAG"
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
inspect_image_if_exists "$IMAGE_TAG"
echo

echo "== Backend image preflight =="
run_backend_image_preflight
echo

echo "== Restart stack =="
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" down --remove-orphans
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --force-recreate
echo

echo "== bot_service container inspect =="
inspect_container_if_exists paidviewer_bot_service
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
show_failure_context
exit 1
