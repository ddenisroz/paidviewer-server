# Repository Guidelines

This file is an internal guide for contributors and agents working in `paidviewer-server`.
If behavior changes, keep the active product docs in `docs/` in sync.

## Project Structure

- `bot_service/`: FastAPI backend. Main layers:
  - `api/` for routes
  - `services/` for business logic
  - `repositories/` for data access
  - `core/` for config/auth
  - `tests/` for backend tests
- `deploy/`: Docker compose files and deploy assets.
- `docs/`: active product and operator docs.
- `scripts/`: project tooling.
- `scripts/dev/`: targeted smoke and support checks that still matter operationally.
- `logs/`: local runtime logs when enabled.

## Active Product Model

- Official TTS modes are only:
  - `cloud`
  - `self_host`
- Official cloud path:
  - `bot_service -> tts-gateway -> provider runtime`
- Official self-host path:
  - `bot_service -> provisioning/pairing -> tts_worker_agent -> local runtime`
- Legacy raw local endpoint support is compatibility-only. Do not treat it as the main user flow.
- Twitch is the main GA platform.
- VK Live is beta, but must still stay technically stable and capability-driven.

## Active Routes And Screens

- Main TTS screens:
  - `/dashboard/tts`
  - `/dashboard/tts/voices`
  - `/tts-player`
- Admin panel route:
  - `/dashboard/admin`
- Admin tabs must stay aligned between direct URLs and tab state:
  - `overview`
  - `runtime`
  - `tts`
  - `accounts`
  - `channels`
  - `logs`
- Legacy admin route `/dashboard/dolbaebadmintts/*` is removed from the active product flow.

## Build, Test, And Development Commands

- Python baseline: `3.12`
- Activate venv on Windows:
  - `.\.venv\Scripts\Activate.ps1`
- Backend local run:
  - `cd bot_service`
  - `python main.py`
- Run migrations:
  - `cd bot_service`
  - `alembic upgrade head`
- Docker dev stack:
  - `.\start-dev.ps1`

## Coding Style

- Python:
  - 4 spaces
  - max line length `120`
  - use `ruff format .` and `ruff check .`
- TypeScript/React:
  - use the repo ESLint and Prettier setup
  - keep components small when possible
  - avoid repeating backend contracts in frontend constants if backend already returns them

## Testing Expectations

- Backend:
  - run `pytest` from `bot_service/`
- For release-sensitive changes, prefer targeted regression before broad changes:
  - TTS routes/contracts
  - VK OAuth and role parity
  - drops/streaks
  - YouTube queue/rewards
  - admin screens

## Security And Configuration

- Do not change `.env` secrets manually in normal refactor work.
- Per-service env files remain the source of runtime configuration.
- Do not hardcode local paths, localhost runtime assumptions, or provider URLs into active user-facing logic.
- External TTS upstream auth uses API keys, not ad-hoc internal tokens.

## Authentication Rules

- User OAuth entrypoints:
  - `/auth/twitch/login`
  - `/auth/vk/login`
- User OAuth callbacks:
  - `/auth/twitch/callback`
  - `/auth/vk/callback`
- Session auth is cookie-based via `session_id`.
- Admin authority source of truth is `users.role='admin'`.

### Bot OAuth

- Bot login routes:
  - `/auth/twitch/bot/login`
  - `/auth/vk/bot/login`
- Bot callback routes:
  - `/auth/twitch/bot/callback`
  - `/auth/vk/bot/callback`
- Bot OAuth is admin-gated.
- Bot tokens live in DB and are the runtime source of truth.

## Product Behavior Notes

- Shared frontend WebSocket is single-leader per user across tabs.
- Browser TTS playback in website mode runs only through `/tts-player`.
- Website-mode TTS requires an active `/tts-player` sink.
- OBS mode requires an active OBS sink.
- TTS/YouTube autoplay must not resume automatically after full page reload.
- YouTube queue bans set queue items to `status='banned'`.
- VK chat badges are passed as image URLs.
- F5 runtime availability must reflect the actual deployment and readiness policy.
- If provider voice CRUD upstreams are unreachable, backend routes should return readable `503` behavior instead of pretending everything is empty and healthy.

## Admin UI Notes

- Only the admin area may receive visible UI/UX changes without affecting the rest of the product design.
- Prefer semantic tokens and existing admin UI building blocks.
- Do not introduce `alert/confirm` in new admin flows.
- Keep destructive actions explicit and deliberate.

## Repository Hygiene

- Keep temp artifacts and debug leftovers out of commits:
  - `__pycache__/`
  - `.pytest_cache/`
  - temp audio files
  - local logs
  - ad-hoc patch files
- Keep text files UTF-8.
- Remove mojibake instead of carrying broken strings forward.

## What To Read First

Before making large changes, read:

1. `docs/README.md`
2. `docs/QUICKSTART.md`

If the task is operational or release-oriented, also read:

1. `docs/release/RELEASE_CHECKLIST.md`
2. `docs/setup/LIVE_SMOKE_RUNBOOK.md`
3. `docs/setup/TTS_SUPPORT_RUNBOOK.md`
