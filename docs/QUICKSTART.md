# Quickstart Для Split Server Repo

Этот файл относится только к `paidviewer-server`: backend, PostgreSQL, Redis и production Docker Compose.

Для твоей текущей схемы без backend-домена используй основную инструкцию:

[IP_ONLY_VERCEL_GUIDE.md](IP_ONLY_VERCEL_GUIDE.md)

## Минимальный VPS Запуск

```bash
sudo mkdir -p /srv/paidviewer/{env,uploads,logs,backups,postgres,redis,bot-data}
sudo chown -R $USER:$USER /srv/paidviewer

sudo mkdir -p /opt/paidviewer
sudo chown -R $USER:$USER /opt/paidviewer
git clone https://github.com/ddenisroz/paidviewer-server.git /opt/paidviewer/server
cd /opt/paidviewer/server

cp deploy/docker/.env.ip-only.example /srv/paidviewer/env/.env
nano /srv/paidviewer/env/.env
```

Запусти smoke-деплой. Он сам проверит compose config, пересоберёт backend image без кеша, пересоздаст контейнеры и дождётся `/health/ready`:

```bash
bash scripts/vps-deploy-smoke.sh
```

## Что Должно Быть В Env

Обязательно замени:

- `POSTGRES_PASSWORD`
- `REDIS_PASSWORD`
- `SECRET_KEY`
- `TOKEN_ENCRYPTION_KEY`
- `YOUR_VERCEL_APP_URL`
- `YOUR_SERVER_IP`

Для первого запуска оставь:

```env
BOT_SERVICE_IMAGE=paidviewer-server:local
BOT_SERVICE_BIND_IP=0.0.0.0
BOT_SERVICE_PORT=8000
```

Интеграции Twitch, VK, YouTube и DonationAlerts можно заполнить позже.

## Обновление

```bash
cd /opt/paidviewer/server
git pull
bash scripts/vps-deploy-smoke.sh
```

## Где Остальные Части

- frontend: `ddenisroz/paidviewer-web`, деплой на Vercel;
- self-host TTS: `ddenisroz/paidviewer-self-host`, запуск на машине пользователя;
- backend runtime state: `/srv/paidviewer`, не хранится в git.
