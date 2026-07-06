# Документация

В `docs/` оставлен только минимальный активный слой.

## Активные документы

1. [IP_ONLY_VERCEL_GUIDE.md](IP_ONLY_VERCEL_GUIDE.md)
2. [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
3. [QUICKSTART.md](QUICKSTART.md)
4. [release/RELEASE_CHECKLIST.md](release/RELEASE_CHECKLIST.md)
5. [setup/LIVE_SMOKE_RUNBOOK.md](setup/LIVE_SMOKE_RUNBOOK.md)
6. [setup/TTS_SUPPORT_RUNBOOK.md](setup/TTS_SUPPORT_RUNBOOK.md)

## Что где искать

- полный локальный запуск всего контура: `QUICKSTART.md`
- production VPS + Vercel + Self Hosted TTS: `DEPLOYMENT_GUIDE.md`
- релизный стоп-лист: `release/RELEASE_CHECKLIST.md`
- обязательный staging/live smoke: `setup/LIVE_SMOKE_RUNBOOK.md`
- типовые проблемы TTS/self-host/VK: `setup/TTS_SUPPORT_RUNBOOK.md`

## Принцип

- один документ на одну задачу
- без производных аудитов и промежуточных планов в активном слое
- без параллельных инструкций с разными словами для одного и того же процесса
- исторический backlog не является частью release tree; если он нужен для исследования, хранить его вне активной документации
