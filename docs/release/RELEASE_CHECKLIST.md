# Release Checklist

## Before deploy

- Python baseline is fixed to `3.12` across `paidviewer_tools`, `tts-gateway`, `f5-tts-service`
- pinned `BOT_SERVICE_IMAGE`, `FRONTEND_IMAGE`, `TTS_GATEWAY_IMAGE`, `F5_TTS_IMAGE` are set
- `docker-compose.prod.yml` validates and contains no host-port conflicts
- migrations apply without manual patching
- `VK Live` and `Twitch` are both GA platform integrations
- canonical admin route is only `/dashboard/admin`
- OAuth callback URLs in provider consoles match the deployed public origin exactly; local Docker uses `/auth/...`, not `/api/auth/...`

## Env contract

- `BACKEND_URL`, `FRONTEND_URL`, `DATABASE_URL`, `REDIS_URL` are filled in for the target environment
- `TTS_GATEWAY_URL`, `TTS_GATEWAY_API_KEY`, `F5_TTS_SERVICE_URL`, `F5_TTS_SERVICE_API_KEY` are set
- `BOT_SERVICE_IMAGE` and `FRONTEND_IMAGE` point to release images, not local `build:` paths
- `TTS_WORKER_AGENT_REQUIRED_VERSION` and `TTS_WORKER_AGENT_RECOMMENDED_VERSION` are configured
- `LOCAL_TTS_ALLOWED_HOSTS` and `LOCAL_TTS_ALLOWED_CIDRS` are configured for the target environment
- provider runtime API keys are accepted from headers only in public paths; query-string keys are not used by product traffic
- provider runtimes are reachable only from gateway/agent networks or loopback bindings, not directly from the public Internet

## Security gate

- OAuth popups cannot give untrusted upstream pages control of the dashboard window
- CORS policies on protected runtime APIs are restricted to the intended trusted callers
- access tokens, refresh tokens, API keys and OAuth `state` values are redacted from logs, Sentry breadcrumbs and support screenshots
- upload endpoints validate size, content type and storage path before persisting user-provided files
- tracked files do not include local backups, screenshots, ad-hoc logs or generated runtime artifacts

## Regression gate

- full backend `pytest` is green
- `frontend` `npm run check:all` is green
- `frontend` `npm run test:run` is green
- `frontend` `npm run build` is green
- `frontend` `npm run check:no-direct-tts-url` is green
- runtime repos `tts-gateway`, `f5-tts-service` pass their local `pytest -q` suites
- `npm audit --audit-level=high` and Python dependency audit have no untriaged high/critical issues
- local Docker compose validates with `docker compose --env-file deploy/docker/compose.local.env -f deploy/docker/docker-compose.local.yml config -q`
- production compose validates with pinned release image variables before any tag is cut

## Data hygiene gate

- create a PostgreSQL backup outside the release tree before deleting data
- run `bot_service/scripts/database_hygiene.py --all` first in preview mode, then with `--yes` only after checking the candidates
- keep real users from `ADMIN_USERS`, active OAuth tokens, TTS settings, commands, overlays, drops and YouTube settings
- delete only test/guest/orphan/runtime-tail rows that are not tied to the current real user or active channel
- run `bot_service/scripts/check_postgresql_data.py` and `bot_service/scripts/user_diagnostics.py` after cleanup

## Smoke order

1. `cloud x f5`
2. `self_host x f5 via tts_worker_agent`
3. `drops duplicate-event/session-boundary`
4. `youtube next/skip/reorder`
5. `vk bot OAuth GA flow`

## Demo gate

- image set is pinned before the demo build is frozen
- `f5-tts-service` dirty state is explicitly confirmed before freezing demo images
- the full staging walkthrough succeeds twice in a row without restart or manual cleanup
- `tts_worker_agent` autostart remains opt-in; demo and production steps do not rely on hidden autostart side effects

## Rollback

- roll back pinned images to the previous tested tags/digests
- roll back the release image set as a whole; do not mix old `core` images with new `cloud-tts` images
- if the issue is isolated to the self-host agent, roll back the required/recommended agent version and temporarily rely on the compatibility path only for support

## Known issues

- raw endpoint mode remains compatibility-only and is not the primary UX
- `VK Live` has a GA smoke gate; platform capability gaps must be represented by explicit capability flags, not beta copy
- large legacy frontend screens still need a separate tech-debt refactor sprint after release
- `f5-tts-service/vendor/F5-TTS` must be explicitly reviewed before any release freeze if its git state is not clean
- real-account OAuth and GPU/model TTS smoke must be completed in a live browser session with the release image set; mock data is not a substitute
