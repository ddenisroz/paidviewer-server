# Деплой Без Домена: VPS По IP + Frontend На Vercel

Эта инструкция для схемы:

```text
браузер -> https://YOUR_VERCEL_APP_URL -> Vercel rewrites/functions -> http://YOUR_SERVER_IP:8000 -> bot_service
```

Важно: с HTTPS-страницы Vercel браузер не может безопасно ходить напрямую в `http://YOUR_SERVER_IP:8000` и `ws://YOUR_SERVER_IP:8000`. Поэтому REST/auth/uploads идут через Vercel rewrites, а WebSocket идёт через Vercel Function bridge.

## 1. Что Нужно От Тебя

Подготовь:

- VPS с публичным IPv4;
- открытый TCP-порт `8000` на VPS;
- GitHub repo `ddenisroz/paidviewer-server`;
- GitHub repo `ddenisroz/paidviewer-web`;
- Vercel account;
- OAuth apps Twitch/VK/DonationAlerts, если эти интеграции нужны.

Запиши два значения:

```text
YOUR_SERVER_IP=123.123.123.123
YOUR_VERCEL_APP_URL=your-project.vercel.app
```

`YOUR_VERCEL_APP_URL` указывай без `https://` в местах, где это прямо написано, и с `https://` в env URL.

Где взять `YOUR_VERCEL_APP_URL`:

1. Создай проект в Vercel из repo `ddenisroz/paidviewer-web`.
2. В настройках проекта выбери root directory `frontend`.
3. Сделай первый deploy, даже если backend env ещё не заполнен.
4. Открой Vercel project -> Deployments -> последний deployment -> домен вида `paidviewer-web-xxxx.vercel.app`.
5. Скопируй домен без `https://` и используй его как `YOUR_VERCEL_APP_URL`.

Если позже добавишь custom domain, просто замени `YOUR_VERCEL_APP_URL` в Vercel env, server `.env` и OAuth callback URLs на новый домен.

## 2. Подготовить VPS

```bash
sudo mkdir -p /srv/paidviewer/{env,uploads,logs,backups,postgres,redis,bot-data}
sudo chown -R $USER:$USER /srv/paidviewer/env /srv/paidviewer/postgres /srv/paidviewer/redis
sudo chown -R 1000:1000 /srv/paidviewer/uploads /srv/paidviewer/logs /srv/paidviewer/backups /srv/paidviewer/bot-data
```

Склонируй backend repo на VPS:

```bash
sudo mkdir -p /opt/paidviewer
sudo chown -R $USER:$USER /opt/paidviewer
git clone https://github.com/ddenisroz/paidviewer-server.git /opt/paidviewer/server
cd /opt/paidviewer/server
```

Скопируй IP-only env:

```bash
cp deploy/docker/.env.ip-only.example /srv/paidviewer/env/.env
nano /srv/paidviewer/env/.env
```

Если `/srv/paidviewer/env/.env` открылся пустым, значит команда `cp` не выполнилась или ты был не в папке repo. Создай файл напрямую из GitHub:

```bash
curl -fsSL https://raw.githubusercontent.com/ddenisroz/paidviewer-server/main/deploy/docker/.env.ip-only.example \
  -o /srv/paidviewer/env/.env
nano /srv/paidviewer/env/.env
```

Замени:

- `YOUR_SERVER_IP`
- `YOUR_VERCEL_APP_URL`
- все `change-me`
- OAuth credentials, если используешь интеграции
- `BOT_SERVICE_IMAGE`

Для первого запуска поставь локальный image tag:

```env
BOT_SERVICE_IMAGE=paidviewer-server:local
```

Сам image соберёт `scripts/vps-deploy-smoke.sh` на шаге запуска. Так меньше риска случайно поднять старый образ.

Позже, когда будет настроена публикация Docker image в GHCR, можно заменить это на tag вида `ghcr.io/ddenisroz/paidviewer-server:<version>`.

Для IP-only режима обязательно:

```env
BOT_SERVICE_BIND_IP=0.0.0.0
BOT_SERVICE_PORT=8000
BACKEND_URL=https://YOUR_VERCEL_APP_URL
FRONTEND_URL=https://YOUR_VERCEL_APP_URL
CORS_ORIGINS=https://YOUR_VERCEL_APP_URL
```

Минимальный набор значений для первого запуска:

```env
PAIDVIEWER_DATA_DIR=/srv/paidviewer
BOT_SERVICE_BIND_IP=0.0.0.0
BOT_SERVICE_PORT=8000

POSTGRES_USER=paidviewer
POSTGRES_PASSWORD=<сильный_пароль_для_postgres>
POSTGRES_DB=paidviewer
REDIS_PASSWORD=<сильный_пароль_для_redis>

BOT_SERVICE_IMAGE=paidviewer-server:local

SECRET_KEY=<openssl_rand_hex_32>
TOKEN_ENCRYPTION_KEY=<fernet_key>

BACKEND_URL=https://YOUR_VERCEL_APP_URL
FRONTEND_URL=https://YOUR_VERCEL_APP_URL
CORS_ORIGINS=https://YOUR_VERCEL_APP_URL
```

Сгенерировать пароли и ключи на VPS:

```bash
openssl rand -base64 32
openssl rand -base64 32
openssl rand -hex 32
docker run --rm python:3.12-slim sh -lc "pip install -q cryptography && python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
```

Первый `openssl rand -base64 32` используй для `POSTGRES_PASSWORD`, второй для `REDIS_PASSWORD`, `openssl rand -hex 32` для `SECRET_KEY`, результат Python-команды для `TOKEN_ENCRYPTION_KEY`.

Интеграции можно оставить пустыми, пока они не нужны:

- `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET`;
- `VK_CLIENT_ID`, `VK_CLIENT_SECRET`;
- `YOUTUBE_API_KEY`;
- `DONATIONALERTS_CLIENT_ID`, `DONATIONALERTS_CLIENT_SECRET`, `DONATIONALERTS_WEBHOOK_SECRET`;
- `ADMIN_USERS`.

Открой порт:

```bash
sudo ufw allow 8000/tcp
```

Если `ufw` не установлен, не используется на VPS или команда падает, открой TCP `8000` в firewall-панели провайдера. Для проверки самого backend на сервере достаточно локального `curl http://127.0.0.1:8000/health/ready`; для Vercel порт должен быть доступен снаружи по `http://YOUR_SERVER_IP:8000`.

## 3. Запустить Backend

```bash
bash scripts/vps-deploy-smoke.sh
```

Если до этого ты уже запускал `docker compose up -d` вручную и видишь в логах
`relation "users" does not exist` или команду контейнера вида
`alembic upgrade ...`, не продолжай ручной `compose up`. Это старый образ.
Сделай:

```bash
cd /opt/paidviewer/server
git pull
bash scripts/vps-deploy-smoke.sh
```

Smoke-скрипт сам пересоберёт `paidviewer-server:local` с `--no-cache`,
проверит, что команда запуска содержит `bootstrap_database.py`, пересоздаст
контейнеры и только потом проверит `/health/ready`.

Проверка с твоего компьютера:

```bash
curl -f http://YOUR_SERVER_IP:8000/health/ready
```

Если health не отвечает, Vercel тоже не сможет достучаться.

## 4. Логи И Защита Диска

Логи на сервере настроены так, чтобы они были доступны для диагностики, но не росли бесконечно.

Docker logs для `postgres`, `redis` и `bot_service` ограничены в `deploy/docker/docker-compose.server.yml`:

```yaml
max-size: "10m"
max-file: "5"
compress: "true"
```

Это значит: Docker хранит не бесконечный поток stdout/stderr, а ограниченный набор файлов примерно до `50 MB` на сервис до сжатия.

Application logs лежат здесь:

```bash
/srv/paidviewer/logs
```

Основной backend log:

```bash
/srv/paidviewer/logs/bot_service.log
```

Security log:

```bash
/srv/paidviewer/logs/security.log
```

Оба файловых лога ротируются. По умолчанию:

- `bot_service.log`: `5 MB` файл + `5` backup-файлов;
- `security.log`: `5 MB` файл + `5` backup-файлов.

Лимиты можно менять в `/srv/paidviewer/env/.env`:

```env
LOG_FILE_MAX_BYTES=5242880
LOG_FILE_BACKUP_COUNT=5
SECURITY_LOG_MAX_BYTES=5242880
SECURITY_LOG_BACKUP_COUNT=5
```

Посмотреть логи:

```bash
docker compose --env-file /srv/paidviewer/env/.env -f deploy/docker/docker-compose.server.yml logs -f bot_service
tail -n 200 /srv/paidviewer/logs/bot_service.log
tail -n 200 /srv/paidviewer/logs/security.log
du -sh /srv/paidviewer/logs
```

Если нужно временно больше подробностей:

```env
LOG_LEVEL=DEBUG
LOG_FILE_LEVEL=INFO
```

После изменения env перезапусти backend:

```bash
docker compose --env-file /srv/paidviewer/env/.env -f deploy/docker/docker-compose.server.yml up -d
```

## 5. Настроить Vercel Rewrites

В repo `paidviewer-web` уже есть готовый:

```powershell
frontend\vercel.json
```

В `frontend/vercel.json` не должно быть реального IP. Этот файл можно коммитить в публичный repo: он содержит только внутренние rewrites на Vercel Function proxy.

Vercel project settings:

- Framework preset: `Vite`
- Root directory: `frontend`
- Build command: `npm run build`
- Output directory: `dist`
- Fluid Compute: включить, если проект создан до 23.04.2025 или WebSocket bridge не стартует

Production env в Vercel:

```env
VITE_BOT_SERVICE_URL=
VITE_API_BASE_URL=
VITE_API_URL=
VITE_BOT_SERVICE_WS_URL=wss://YOUR_VERCEL_APP_URL/api
VITE_FRONTEND_URL=https://YOUR_VERCEL_APP_URL
VITE_LOCAL_TTS_AGENT_URL=
BOT_SERVICE_HTTP_TARGET=http://YOUR_SERVER_IP:8000
BOT_SERVICE_WS_TARGET=ws://YOUR_SERVER_IP:8000
```

Пустой `VITE_BOT_SERVICE_URL` важен: frontend будет обращаться к своему Vercel-origin. Реальный IP сервера хранится только в server-side Vercel env `BOT_SERVICE_HTTP_TARGET` и `BOT_SERVICE_WS_TARGET`, а не в публичном репозитории.

## 6. OAuth Callback URLs

В провайдерах указывай Vercel URL, не raw IP:

```text
https://YOUR_VERCEL_APP_URL/auth/twitch/callback
https://YOUR_VERCEL_APP_URL/auth/twitch/bot/callback
https://YOUR_VERCEL_APP_URL/auth/vk/callback
https://YOUR_VERCEL_APP_URL/auth/vk/bot/callback
https://YOUR_VERCEL_APP_URL/donationalerts/callback
```

Так cookies будут выставляться на HTTPS-домен Vercel, а не на небезопасный HTTP IP.

## 7. Проверка После Деплоя

Открой:

```text
https://YOUR_VERCEL_APP_URL
```

Проверь:

- `/api/...` запросы в DevTools идут на Vercel URL, а не на `http://IP`;
- login Twitch/VK возвращает обратно на Vercel URL;
- WebSocket URL начинается с `wss://YOUR_VERCEL_APP_URL/api/ws/...`;
- uploads доступны через `https://YOUR_VERCEL_APP_URL/static/uploads/...`;
- `https://YOUR_VERCEL_APP_URL/health/ready` возвращает backend health.

## 8. Ограничения IP-Only Режима

- Порт `8000` на VPS будет публичным.
- Без домена нельзя получить нормальный публичный TLS-сертификат для backend IP.
- Если Vercel WebSocket bridge выключен или env `BOT_SERVICE_WS_TARGET` не задан, realtime-функции не будут работать.
- Vercel WebSockets сейчас работают через Vercel Functions beta; соединения могут закрываться по лимитам функции, клиент должен переподключаться.
- Для production с меньшим количеством компромиссов лучше позже добавить домен хотя бы на backend.

## 9. Обновление

Backend:

```bash
docker exec paidviewer_postgres pg_dump -U paidviewer paidviewer > /srv/paidviewer/backups/paidviewer-$(date +%F-%H%M%S).sql
cd /opt/paidviewer/server
git pull
bash scripts/vps-deploy-smoke.sh
curl -f http://YOUR_SERVER_IP:8000/health/ready
```

Frontend:

- push в `paidviewer-web/main`;
- Vercel сам пересоберёт проект.
