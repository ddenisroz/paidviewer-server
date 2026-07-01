# Paidviewer Server

Production backend repository for Paidviewer.

Contains:

- `bot_service` - FastAPI backend, integrations, bots, worker control plane;
- `deploy` - Docker Compose and reverse proxy examples;
- `docs` - deployment, smoke and release guides;
- `scripts` - migration and maintenance helpers.

Frontend lives in `paidviewer-web`. Self Hosted TTS agent lives in `paidviewer-self-host`.

## Deploy

1. Prepare VPS directories:

```bash
sudo mkdir -p /srv/paidviewer/{env,uploads,logs,backups,postgres,redis,bot-data}
sudo chown -R $USER:$USER /srv/paidviewer
```

2. Copy env template:

```bash
cp deploy/docker/.env.server.example /srv/paidviewer/env/.env
```

3. Fill real values in `/srv/paidviewer/env/.env`.

4. Start:

```bash
docker compose --env-file /srv/paidviewer/env/.env -f deploy/docker/docker-compose.server.yml up -d
```

5. Put Caddy or Nginx in front of `127.0.0.1:8000`.

See [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) for the full guide.

## Required Production Variables

Minimum required:

- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_DB`
- `REDIS_PASSWORD`
- `BOT_SERVICE_IMAGE`
- `SECRET_KEY`
- `TOKEN_ENCRYPTION_KEY`
- `BACKEND_URL`
- `FRONTEND_URL`
- `CORS_ORIGINS`

Integration variables are optional until the feature is used: Twitch, VK Live, YouTube, DonationAlerts.

## Storage

Runtime state is outside git:

- uploads: `/srv/paidviewer/uploads`
- logs: `/srv/paidviewer/logs`
- backups: `/srv/paidviewer/backups`
- postgres: `/srv/paidviewer/postgres`
- redis: `/srv/paidviewer/redis`

Docker logs and app logs are rotated by default.

## Update

```bash
docker exec paidviewer_postgres pg_dump -U paidviewer paidviewer > /srv/paidviewer/backups/paidviewer-$(date +%F-%H%M%S).sql
docker compose --env-file /srv/paidviewer/env/.env -f deploy/docker/docker-compose.server.yml pull
docker compose --env-file /srv/paidviewer/env/.env -f deploy/docker/docker-compose.server.yml up -d
curl -f https://api.example.com/health/ready
```
