# TTS Support Runbook

Это короткая памятка для типовых проблем TTS.

Если ты обычный пользователь проекта, а не support/ops, чаще всего тебе нужен только раздел с симптомом и простым действием.

## `cloud_slot_required`

Что это значит:
- cloud-режим сейчас недоступен для этого пользователя

Как выглядит:
- `GET /api/tts/status` возвращает `slot_allowed=false`

Что делать:
- перевести пользователя в `self_host`
- использовать provisioning bundle + `tts_worker_agent`

## `version_mismatch`

Что это значит:
- установленный `tts_worker_agent` слишком старый

Как выглядит:
- агент получает `409` на activation или poll

Что делать:
- сравнить `required_agent_version` из bundle с версией установленного агента
- обновить агент
- понижать required version только как временный rollback

## `provider_unreachable`

Что это значит:
- runtime недоступен или не отвечает вовремя

Что проверить:
- `endpoint_url`
- `api_key`
- health runtime
- firewall / сеть

Если это `cloud`:
- проверить `tts-gateway`
- проверить provider runtime

Если это `self_host`:
- проверить локальный runtime у пользователя
- проверить `http://127.0.0.1:46321/diagnostics`

## `pairing_expired`

Что это значит:
- provisioning bundle или pairing token уже недействителен

Как выглядит:
- агент не может активироваться
- backend возвращает отказ на activation/poll до появления runtime health

Что делать:
- создать новый provisioning bundle в интерфейсе
- проверить, что пользователь не импортирует старый bundle из загрузок
- убедиться, что системное время на машине пользователя не уехало далеко от backend времени

## `worker_offline`

Что это значит:
- backend знает о worker, но он давно не опрашивал сервер

Что делать:
- попросить пользователя открыть локальную диагностику
- перезапустить `tts_worker_agent`
- проверить bundle import, `worker_token`, версию агента и доступность backend URL

## `voice_missing`

Что это значит:
- runtime не нашёл нужный голос

Что делать:
- проверить provider
- проверить voice id / voice name
- проверить, что voice storage не потерян
- проверить, что F5 runtime видит актуальный каталог голосов

## `vk_bot_auth_failed`

Что это значит:
- VK bot OAuth завершился ошибкой

Типовые коды:
- `access_denied`
- `invalid_state`
- `save_failed`
- `restart_failed`

Что делать:
1. проверить state cookie и callback URL
2. проверить, что токен сохранился в backend
3. проверить, смог ли bot runtime реально подняться после callback

Важно:
- `restart_failed` не считается успешной авторизацией
- это отдельный runtime-инцидент, а не “почти success”

## OAuth redirect mismatch

Что это значит:
- провайдер отправил callback не на тот origin/path, который ожидает текущий runtime

Типовой локальный Docker-контур:
- `http://localhost/auth/twitch/callback`
- `http://localhost/auth/twitch/bot/callback`
- `http://localhost/auth/vk/callback`
- `http://localhost/auth/vk/bot/callback`
- `http://localhost/donationalerts/callback`

Что делать:
- открыть UI через тот же origin, который указан в OAuth-приложении
- не смешивать `localhost` и `127.0.0.1`
- для Docker core использовать `/auth/...`; `/api/auth/...` оставлять только для осознанного backend-direct сценария
