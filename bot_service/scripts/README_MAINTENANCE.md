# Скрипты обслуживания backend

В корне `bot_service/scripts/` лежат только рабочие maintenance-скрипты для ежедневного использования. Отладочные вспомогательные скрипты вынесены в `bot_service/scripts/dev/`, а старые destructive-скрипты — в `bot_service/scripts/archive/legacy/`.

## Что должно лежать в корне

- `database_hygiene.py`
- `delete_users.py`
- `db_console.py`
- `show_db_structure.py`
- `check_postgresql_data.py`
- `run_check.py`
- `README_MAINTENANCE.md`

## Где искать остальное

- `scripts/dev/` — диагностика, проверка токенов, проверка сессий, локальные вспомогательные утилиты
- `scripts/archive/legacy/` — старые destructive-сценарии, которые не должны использоваться в обычном workflow

## Безопасное удаление пользователей

Для точечного удаления пользователя используй `delete_users.py`. Этот скрипт делает preview по умолчанию и не требует ручного SQL.

Просмотр списка:

```powershell
python scripts/delete_users.py --list
```

Preview без удаления:

```powershell
python scripts/delete_users.py --user-id 42
python scripts/delete_users.py --twitch some_channel
python scripts/delete_users.py --vk some_vk_channel
```

Фактическое удаление:

```powershell
python scripts/delete_users.py --user-id 42 --yes
```

## Гигиена БД: orphan-записи и старые неактивные сессии

`database_hygiene.py` нужен для трёх задач:
- удалить записи с `user_id`, которого уже нет в `users`;
- удалить legacy `session_id` записи из active user-only таблиц, включая `youtube_queue` и session-scoped `drops_*` хвосты;
- очистить старые неактивные сессии по retention-политике.

Preview:

```powershell
python scripts/database_hygiene.py
python scripts/database_hygiene.py --orphan-users
python scripts/database_hygiene.py --legacy-session-records
python scripts/database_hygiene.py --inactive-sessions --inactive-session-days 7
```

Очистка:

```powershell
python scripts/database_hygiene.py --yes
python scripts/database_hygiene.py --orphan-users --yes
python scripts/database_hygiene.py --legacy-session-records --yes
python scripts/database_hygiene.py --inactive-sessions --inactive-session-days 7 --yes
```

## Опасные legacy-скрипты

Перед запуском destructive-сценариев сначала используй preview/dry-run, если он есть:

```powershell
python scripts/archive/legacy/clear_database.py clear --dry-run
python scripts/archive/legacy/reset_db.py --dry-run
```

Фактический destructive запуск делай только осознанно:

```powershell
python scripts/archive/legacy/clear_database.py clear --yes
python scripts/archive/legacy/reset_db.py --yes
```

## Единый launcher для проверок

Для типовых безопасных проверок используй `run_check.py`:

```powershell
cd bot_service
python scripts/run_check.py --list
python scripts/run_check.py tts-status 1
python scripts/run_check.py admin
```

Этот launcher не делает destructive-операций и только проксирует безопасные проверки из корня и `scripts/dev/`.
