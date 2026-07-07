# Paidviewer Deployment Guide

This guide is the source of truth for the split production setup:

- server: `bot_service` on a VPS with PostgreSQL and Redis;
- web: `frontend` on Vercel;
- self-host TTS: `tts_worker_agent` plus local `f5-tts-service` on the user's machine.

## Repository Split

Use three repositories:

| Repository | Content | Deploy target |
| --- | --- | --- |
| `ddenisroz/paidviewer-server` | `bot_service`, `deploy`, backend migrations/scripts/docs | VPS Docker Compose |
| `ddenisroz/paidviewer-web` | `frontend` | Vercel |
| `ddenisroz/paidviewer-self-host` | `tts_worker_agent`, release scripts, user README | GitHub Releases |

Do not commit server runtime state: `.env`, `logs`, `uploads`, `backups`, `tmp`, caches or local database dumps.

## VPS Layout

Create one persistent root:

```bash
sudo mkdir -p /srv/paidviewer/{env,uploads,logs,backups,postgres,redis,bot-data}
sudo chown -R $USER:$USER /srv/paidviewer
```

Copy `deploy/docker/.env.server.example` to `/srv/paidviewer/env/.env` and fill real values.

Important URLs:

```env
BACKEND_URL=https://api.example.com
FRONTEND_URL=https://app.example.com
CORS_ORIGINS=https://app.example.com
```

OAuth callback URLs must use the backend domain:

```env
TWITCH_REDIRECT_URI=https://api.example.com/auth/twitch/callback
TWITCH_BOT_REDIRECT_URI=https://api.example.com/auth/twitch/bot/callback
VK_REDIRECT_URI=https://api.example.com/auth/vk/callback
VK_BOT_REDIRECT_URI=https://api.example.com/auth/vk/bot/callback
DONATIONALERTS_REDIRECT_URI=https://api.example.com/donationalerts/callback
```

## Server Start

From the server repository:

```bash
bash scripts/vps-deploy-smoke.sh
```

The smoke script validates compose config, rebuilds the backend image with the configured `BOT_SERVICE_IMAGE` tag, recreates containers and waits for `/health/ready`.

Expose the backend through Caddy or Nginx. A Caddy example is in `deploy/Caddyfile.example`.

Check:

```bash
curl -f https://api.example.com/health/ready
```

## Vercel

Import the `paidviewer-web` repository in Vercel.

Set production env:

```env
VITE_BOT_SERVICE_URL=https://api.example.com
VITE_BOT_SERVICE_WS_URL=wss://api.example.com
VITE_FRONTEND_URL=https://app.example.com
VITE_LOCAL_TTS_AGENT_URL=
```

The Vite config must expose `VITE_BOT_SERVICE_` and `VITE_API_` prefixes. This repository already does that.

## Self Hosted TTS

The server never connects directly to a user's local runtime. The flow is:

```text
frontend -> bot_service -> worker provisioning -> tts_worker_agent -> f5-tts-service
```

User flow:

1. Open Self Hosted TTS in the dashboard.
2. Download the Self Hosted release.
3. Download connection settings.
4. Run `f5-tts-service` locally at `http://127.0.0.1:8011`.
5. Run `tts_worker_agent` with the downloaded provisioning bundle.
6. Check that the worker is `online`.

The release placeholder is:

```text
https://github.com/paidviewer/self-hosted-tts/releases/latest
```

## Logs And Disk Safety

Docker logs are bounded in `docker-compose.server.yml`:

- `max-size=10m`
- `max-file=5`
- `compress=true`

Application logs live in `/srv/paidviewer/logs`.

`bot_service.log` and `security/security.log` use file rotation. Default security log limit:

```env
SECURITY_LOG_MAX_BYTES=5242880
SECURITY_LOG_BACKUP_COUNT=5
```

Uploads live in `/srv/paidviewer/uploads` and are served by backend paths such as `/static/uploads/...`.

## Backups

Before every update:

```bash
docker exec paidviewer_postgres pg_dump -U paidviewer paidviewer > /srv/paidviewer/backups/paidviewer-$(date +%F-%H%M%S).sql
```

Suggested retention:

- daily backups: 7 days;
- weekly backups: 4 weeks;
- keep manual release backups until the next successful release.

## Updates

Server:

```bash
cd /opt/paidviewer/server
git pull
bash scripts/vps-deploy-smoke.sh
curl -f https://api.example.com/health/ready
```

Web:

- push to `paidviewer-web`;
- Vercel deploys automatically;
- verify login, API calls and WebSocket connection.

Self-host:

- download the latest GitHub release;
- keep the existing provisioning/config;
- restart runtime and worker agent;
- verify worker status in the dashboard.

## Cleanup

Dry run:

```powershell
.\scripts\dev\cleanup_worktree.ps1
```

Apply:

```powershell
.\scripts\dev\cleanup_worktree.ps1 -Apply
```

The cleanup script is allowlist-based. It removes backend caches, logs, temp dirs and build output. It does not remove `.env`, `.venv`, uploads or `/srv/paidviewer` runtime data.
