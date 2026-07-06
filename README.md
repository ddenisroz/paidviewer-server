# Paidviewer Server

Production backend-репозиторий Paidviewer.

Содержит:

- `bot_service` - FastAPI backend, интеграции, боты и worker control plane;
- `deploy` - Docker Compose и примеры reverse proxy;
- `docs` - инструкции по деплою, smoke-проверкам и релизу;
- `scripts` - миграции и сервисные скрипты.

Frontend находится в `paidviewer-web`. Self Hosted TTS agent находится в `paidviewer-self-host`.

## Деплой

1. Подготовить директории на VPS:

```bash
sudo mkdir -p /srv/paidviewer/{env,uploads,logs,backups,postgres,redis,bot-data}
sudo chown -R $USER:$USER /srv/paidviewer
```

2. Скопировать env-шаблон:

```bash
cp deploy/docker/.env.server.example /srv/paidviewer/env/.env
```

3. Заполнить реальные значения в `/srv/paidviewer/env/.env`.

4. Запустить:

```bash
docker compose --env-file /srv/paidviewer/env/.env -f deploy/docker/docker-compose.server.yml up -d
```

5. Поставить Caddy или Nginx перед `127.0.0.1:8000`.

Полная инструкция: [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md).

Если backend будет без домена и только по IP, используй отдельный сценарий: [docs/IP_ONLY_VERCEL_GUIDE.md](docs/IP_ONLY_VERCEL_GUIDE.md).

## Обязательные Production-Переменные

Минимально нужны:

- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_DB`
- `REDIS_PASSWORD`
- `BOT_SERVICE_IMAGE` (`paidviewer-server:local` для первого VPS-запуска)
- `SECRET_KEY`
- `TOKEN_ENCRYPTION_KEY`
- `BACKEND_URL`
- `FRONTEND_URL`
- `CORS_ORIGINS`

Переменные интеграций можно заполнить позже, когда понадобится конкретная функция: Twitch, VK Live, YouTube, DonationAlerts.

## Хранилище

Runtime-состояние хранится вне git:

- uploads: `/srv/paidviewer/uploads`
- logs: `/srv/paidviewer/logs`
- backups: `/srv/paidviewer/backups`
- postgres: `/srv/paidviewer/postgres`
- redis: `/srv/paidviewer/redis`

Docker-логи и app-логи ротируются по умолчанию.

## Обновление

```bash
docker exec paidviewer_postgres pg_dump -U paidviewer paidviewer > /srv/paidviewer/backups/paidviewer-$(date +%F-%H%M%S).sql
docker compose --env-file /srv/paidviewer/env/.env -f deploy/docker/docker-compose.server.yml pull
docker compose --env-file /srv/paidviewer/env/.env -f deploy/docker/docker-compose.server.yml up -d
curl -f https://api.example.com/health/ready
```
