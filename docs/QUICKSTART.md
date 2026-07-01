# Быстрый старт

Этот документ описывает запуск **всего проекта**, а не только `bot_service` и `frontend`.

Под “весь проект” здесь понимается:

- `postgres`
- `redis`
- `bot_service`
- `frontend`
- `tts-gateway`
- `f5-tts-service`
- `tts_worker_agent` при проверке `self_host`

## Требования

- Python `3.12`
- Node.js `20+`
- Docker Desktop + Docker Compose
- PostgreSQL и Redis, если запускаешь не через docker compose

## Репозитории

- основной продукт: [paidviewer_tools](/H:/Programming/raw_code/AI/Python/paidviewer_tools)
- cloud gateway: [tts-gateway](/H:/Programming/raw_code/AI/Python/tts-gateway)
- F5 runtime: [f5-tts-service](/H:/Programming/raw_code/AI/Python/f5-tts-service)

## Рекомендуемый путь: лёгкий Docker-контур

Это основной локальный сценарий для dashboard-разработки. Он не собирает и не запускает тяжёлый F5 runtime.

### 1. Подготовь основной репозиторий
Для основного Docker-сценария локальная установка Python-зависимостей и `npm install` не нужны.

Достаточно перейти в основной репозиторий:

```powershell
cd H:\Programming\raw_code\AI\Python\paidviewer_tools
```

### 2. Подготовь `.env`

Если `.env` уже настроены, **не перезаписывай их**.

Если файлов нет:

```powershell
Copy-Item bot_service/.env.example bot_service/.env
Copy-Item frontend/.env.example frontend/.env
```

Минимум для `bot_service/.env`:

- `DATABASE_URL`
- `REDIS_URL`
- `SECRET_KEY`
- `TWITCH_CLIENT_ID`
- `TWITCH_CLIENT_SECRET`
- `VK_CLIENT_ID`
- `VK_CLIENT_SECRET`
- `TTS_GATEWAY_URL`
- `TTS_GATEWAY_API_KEY`
- `F5_TTS_SERVICE_URL`
- `F5_TTS_SERVICE_API_KEY`

### 3. Подними локальный core-контур

```powershell
cd H:\Programming\raw_code\AI\Python\paidviewer_tools
.\start-dev.ps1
```

`start-dev.ps1` теперь работает в быстром режиме по умолчанию:

- не делает принудительный `down`, если ты явно не попросил `-Reset`
- не делает принудительный rebuild, если ты явно не попросил `-Build`
- умеет поднимать только нужные сервисы через `-Services`

Контур поднимет:

- `postgres` на `5432`
- `redis` на `6379`
- `bot_service` на `8000`
- `frontend` на `80`

Если один из host-портов уже занят локальным сервисом, переопредели только внешний порт перед запуском. Внутри Docker сервисы всё равно общаются по стандартным портам:

```powershell
$env:POSTGRES_HOST_PORT="15432"
$env:REDIS_HOST_PORT="16379"
$env:BOT_SERVICE_HOST_PORT="18000"
$env:TTS_GATEWAY_HOST_PORT="18010"
$env:F5_TTS_SERVICE_HOST_PORT="18011"
$env:FRONTEND_HOST_PORT="8080"
.\start-dev.ps1
```

### 4. Опционально включи TTS-профиль

Fake TTS профиль нужен для проверки UI, gateway и synth-маршрута без загрузки тяжёлых model runtimes:

```powershell
.\start-dev.ps1 -WithCloudTtsFake
```

Полный TTS-профиль собирает и запускает тяжёлый F5 runtime. Используй его только для TTS smoke или разработки TTS:

```powershell
.\start-dev.ps1 -WithCloudTtsReal
```

Если менялся только один сервис, лучше не гонять весь стек:

```powershell
.\start-dev.ps1 -WithCloudTtsReal -Services bot_service
.\start-dev.ps1 -WithCloudTtsReal -Services tts_service
.\start-dev.ps1 -WithCloudTtsReal -Build -Services tts_service
```

Полный жёсткий перезапуск нужен только когда действительно надо пересобрать всё или очистить старые контейнеры:

```powershell
.\start-dev.ps1 -WithCloudTtsReal -Reset
.\start-dev.ps1 -WithCloudTtsReal -Reset -Build
```

Полный профиль добавит:

- `tts-gateway` на `8010`
- `f5-tts-service` на `8011`

### 5. Зафиксируй локальный origin для OAuth

Локально открывай приложение только через:

- `http://localhost`

Не смешивай `localhost` и `127.0.0.1`: для OAuth это разные origin, и это ломает cookie/state-проверку.

Для Docker core открывай приложение через `http://localhost`, поэтому локальные redirect URI у провайдеров должны быть такими:

- `http://localhost/auth/twitch/callback`
- `http://localhost/auth/twitch/bot/callback`
- `http://localhost/auth/vk/callback`
- `http://localhost/auth/vk/bot/callback`
- `http://localhost/donationalerts/callback`

Если запускаешь backend напрямую без nginx, можно использовать `http://localhost:8000/auth/...`, но тогда тот же origin должен быть указан в настройках OAuth-приложений.

`web-push URL` в VK Live не является OAuth callback и настраивается отдельно.

### 6. Проверь базовые точки

- `http://localhost`
- `http://localhost:8000/health`
- `http://localhost:8000/api/tts/health?provider=f5` только если включён TTS-профиль
- `http://localhost:8010/health/ready` для `-WithCloudTtsFake` или `-WithCloudTtsReal`
- `http://localhost:8011/health/ready` для `-WithCloudTtsFake` и `-WithCloudTtsReal`

Официальный локальный путь теперь только `start-dev.ps1`, который использует `docker-compose.prod.yml + docker-compose.local.yml`.

## Где смотреть логи

После `.\start-dev.ps1` локальный стек автоматически зеркалит Docker-логи в:

```text
paidviewer_tools/logs/docker/
```

Основные файлы:

- `logs/docker/bot_service.log`
- `logs/docker/frontend.log`
- `logs/docker/postgres.log`
- `logs/docker/redis.log`
- `logs/docker/tts_gateway.log`
- `logs/docker/tts_service.log`

Это основной локальный путь для диагностики из IDE. Внутренние Docker log-файлы вручную читать не нужно.

## Безопасная остановка и очистка Docker

Обычная остановка не удаляет контейнеры, volumes, БД и model cache:

```powershell
.\stop-dev.ps1
```

Убрать stopped containers/orphans, но сохранить volumes:

```powershell
.\stop-dev.ps1 -CleanContainers
```

Освободить место от dangling `<none>` images и build cache:

```powershell
.\stop-dev.ps1 -PruneImages
```

Volumes удаляй только после бэкапа. Там могут быть локальные пользователи, токены, Postgres и кэши моделей:

```powershell
.\stop-dev.ps1 -PruneVolumes -ConfirmVolumes
```

## Вариант B. Запуск self-host агента

Основной стек остаётся Docker-first, но `tts_worker_agent` по своей природе запускается отдельно на машине пользователя.

Термины:

- `server host` — наш управляемый серверный runtime: `frontend`, `bot_service`, `tts-gateway`, `f5-tts-service`
- `self-host` — локальный runtime пользователя через `tts_worker_agent`

## Если нужен именно локальный dev без Docker

Этот путь больше не считается основным стартовым сценарием.

Используй его только если осознанно отлаживаешь backend/frontend вне контейнеров.

## Self-host путь через `tts_worker_agent`

Если нужно проверить `self_host`, поднимай агент отдельно. Автозапуск теперь **только opt-in**.

```powershell
cd H:\Programming\raw_code\AI\Python\paidviewer_tools\tts_worker_agent
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python.exe .\main.py --config .\config.json
```

Активация:

1. Открой `Local TTS` в интерфейсе Paidviewer
2. Скачай provisioning bundle
3. Выполни pairing flow
4. Проверь локальную диагностику:
   - `http://127.0.0.1:46321/health`
   - `http://127.0.0.1:46321/diagnostics`

Если в self-host нужно отдельно обрабатывать English inside Russian, можно оставить `providers.f5.endpoint_url` на `Misha RU`, а bilingual runtime указать в `providers.f5.mixed_language_endpoint_url`.

Если нужен installer-managed автозапуск, это отдельное явное действие:

```powershell
.\install-agent.ps1 -EnableAutostart -StartNow
```

## Минимальная последовательность проверки после запуска

1. Открой UI и войди в систему
2. Проверь `/api/tts/health` и `/api/tts/status`
3. Прогони один `cloud F5` synth
4. Если нужен self-host smoke, подними `tts_worker_agent` и прогони `self_host F5`
5. Проверь YouTube queue, drops и VK bot status

## Перед релизом

- [release/RELEASE_CHECKLIST.md](/H:/Programming/raw_code/AI/Python/paidviewer_tools/docs/release/RELEASE_CHECKLIST.md)
- [setup/LIVE_SMOKE_RUNBOOK.md](/H:/Programming/raw_code/AI/Python/paidviewer_tools/docs/setup/LIVE_SMOKE_RUNBOOK.md)
- [setup/TTS_SUPPORT_RUNBOOK.md](/H:/Programming/raw_code/AI/Python/paidviewer_tools/docs/setup/TTS_SUPPORT_RUNBOOK.md)
