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

## 2. Подготовить VPS

```bash
sudo mkdir -p /srv/paidviewer/{env,uploads,logs,backups,postgres,redis,bot-data}
sudo chown -R $USER:$USER /srv/paidviewer
```

Скопируй IP-only env:

```bash
cp deploy/docker/.env.ip-only.example /srv/paidviewer/env/.env
nano /srv/paidviewer/env/.env
```

Замени:

- `YOUR_SERVER_IP`
- `YOUR_VERCEL_APP_URL`
- все `change-me`
- OAuth credentials, если используешь интеграции
- `BOT_SERVICE_IMAGE`

Для IP-only режима обязательно:

```env
BOT_SERVICE_BIND_IP=0.0.0.0
BOT_SERVICE_PORT=8000
BACKEND_URL=https://YOUR_VERCEL_APP_URL
FRONTEND_URL=https://YOUR_VERCEL_APP_URL
CORS_ORIGINS=https://YOUR_VERCEL_APP_URL
```

Открой порт:

```bash
sudo ufw allow 8000/tcp
```

## 3. Запустить Backend

```bash
docker compose --env-file /srv/paidviewer/env/.env -f deploy/docker/docker-compose.server.yml up -d
docker compose --env-file /srv/paidviewer/env/.env -f deploy/docker/docker-compose.server.yml ps
```

Проверка с твоего компьютера:

```bash
curl -f http://YOUR_SERVER_IP:8000/health/ready
```

Если health не отвечает, Vercel тоже не сможет достучаться.

## 4. Настроить Vercel Rewrites

В repo `paidviewer-web` скопируй:

```powershell
Copy-Item frontend\vercel.ip-only.example.json frontend\vercel.json
```

В `frontend/vercel.json` замени все `YOUR_SERVER_IP` на IP VPS.

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
BOT_SERVICE_WS_TARGET=ws://YOUR_SERVER_IP:8000
```

Пустой `VITE_BOT_SERVICE_URL` важен: frontend будет обращаться к своему Vercel-origin, а Vercel уже проксирует запросы на IP сервера.

## 5. OAuth Callback URLs

В провайдерах указывай Vercel URL, не raw IP:

```text
https://YOUR_VERCEL_APP_URL/auth/twitch/callback
https://YOUR_VERCEL_APP_URL/auth/twitch/bot/callback
https://YOUR_VERCEL_APP_URL/auth/vk/callback
https://YOUR_VERCEL_APP_URL/auth/vk/bot/callback
https://YOUR_VERCEL_APP_URL/donationalerts/callback
```

Так cookies будут выставляться на HTTPS-домен Vercel, а не на небезопасный HTTP IP.

## 6. Проверка После Деплоя

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

## 7. Ограничения IP-Only Режима

- Порт `8000` на VPS будет публичным.
- Без домена нельзя получить нормальный публичный TLS-сертификат для backend IP.
- Если Vercel WebSocket bridge выключен или env `BOT_SERVICE_WS_TARGET` не задан, realtime-функции не будут работать.
- Vercel WebSockets сейчас работают через Vercel Functions beta; соединения могут закрываться по лимитам функции, клиент должен переподключаться.
- Для production с меньшим количеством компромиссов лучше позже добавить домен хотя бы на backend.

## 8. Обновление

Backend:

```bash
docker exec paidviewer_postgres pg_dump -U paidviewer paidviewer > /srv/paidviewer/backups/paidviewer-$(date +%F-%H%M%S).sql
docker compose --env-file /srv/paidviewer/env/.env -f deploy/docker/docker-compose.server.yml pull
docker compose --env-file /srv/paidviewer/env/.env -f deploy/docker/docker-compose.server.yml up -d
curl -f http://YOUR_SERVER_IP:8000/health/ready
```

Frontend:

- push в `paidviewer-web/main`;
- Vercel сам пересоберёт проект.
