"""
VK Live HTTP Polling клиент для получения сообщений из чата
Использует GET /v1/chat/messages вместо WebSocket
"""
import asyncio
import aiohttp
import logging
import time
import os
import re
from typing import Optional, Callable, Dict, Set

from utils.vk_channel_url import extract_vk_channel_slug
from utils.vk_chat_parser import (
    build_message_text_and_emotes,
    extract_vk_badge_urls,
    extract_vk_mentioned_users,
    extract_vk_reply_metadata,
    normalize_parts,
)

logger = logging.getLogger(__name__)
_VK_INSECURE_SSL = os.getenv("VK_INSECURE_SSL", "false").strip().lower() in {"1", "true", "yes", "on"}


class VKLiveHTTPPolling:
    """HTTP polling клиент для VK Live чата (альтернатива WebSocket)"""
    PROD_API_BASE_URL = "https://api.live.vkvideo.ru"
    DEV_API_BASE_URL = "https://apidev.live.vkvideo.ru"
    # Default to dev API per VK docs.
    API_BASE_URL = DEV_API_BASE_URL

    def __init__(
        self,
        access_token: str,
        channel_url: str,
        user_id: Optional[int] = None,
        token_refresh_mode: str = "user",
    ):
        """
        Args:
            access_token: VK Live access token
            channel_url: URL канала (например, "yourchy")
            user_id: owner user id for user-token refresh mode
            token_refresh_mode: "user" (default) or "bot"
        """
        self.access_token = access_token
        self.channel_url = channel_url
        self.user_id = user_id
        self.token_refresh_mode = token_refresh_mode
        self.is_running = False
        self.poll_task = None
        self.message_handler: Optional[Callable] = None
        self.seen_message_ids: Set[int] = set()  # Для предотвращения дубликатов
        self.last_message_time: int = 0  # Timestamp последнего сообщения
        self.error_count: int = 0  # Счетчик последовательных ошибок
        self.max_errors: int = 10  # Максимум ошибок перед увеличением интервала
        # Use instance-level API base to allow safe fallback.
        self.api_base_url = self.API_BASE_URL
        self.refresh_cooldown_seconds: int = 15
        self._last_refresh_attempt_monotonic: float = 0.0
        self._last_chat_404_notice_monotonic: float = 0.0
        self._smile_map: Dict[str, Dict] = {}
        self._smile_map_updated_at: float = 0.0
        self._smile_map_ttl_seconds: int = 300

    def _format_channel_url(self, channel_url: str) -> str:
        if not channel_url:
            return channel_url
        if channel_url.startswith('http://') or channel_url.startswith('https://'):
            return channel_url
        return f"https://live.vkvideo.ru/{channel_url}"

    def _format_chat_channel(self, channel_url: str) -> str:
        slug = extract_vk_channel_slug(channel_url)
        return slug or channel_url

    def _get_connector(self) -> aiohttp.TCPConnector:
        if 'apidev.' in self.api_base_url and _VK_INSECURE_SSL:
            import ssl
            ssl_context = ssl.create_default_context()
            logger.warning("VK HTTP polling SSL verification disabled via VK_INSECURE_SSL=true")
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            return aiohttp.TCPConnector(ssl=ssl_context)
        return aiohttp.TCPConnector()

    async def start(self, message_handler: Callable):
        """Запустить polling сообщений"""
        if self.is_running:
            logger.warning(f"Polling already running for {self.channel_url}")
            return

        self.message_handler = message_handler
        self.is_running = True
        self.poll_task = asyncio.create_task(self._poll_loop())
        logger.info(f"[OK] Started HTTP polling for VK Live channel: {self.channel_url}")

    async def stop(self):
        """Остановить polling"""
        self.is_running = False
        if self.poll_task:
            self.poll_task.cancel()
            try:
                await self.poll_task
            except asyncio.CancelledError:
                pass
            self.poll_task = None
        logger.info(f"[STOP] Stopped HTTP polling for channel: {self.channel_url}")

    async def _poll_loop(self):
        """Основной цикл polling"""
        poll_interval = 0.5  # Запрашиваем каждые 500ms для быстрой реакции (как Twitch WebSocket)
        max_interval = 30.0  # Максимальный интервал при ошибках (30 секунд)

        try:
            while self.is_running:
                try:
                    await self._fetch_and_process_messages()
                    # Успешный запрос - сбрасываем счетчик ошибок
                    if self.error_count > 0:
                        logger.info(f"[OK] VK Live polling recovered after {self.error_count} errors")
                        self.error_count = 0

                except asyncio.CancelledError:
                    raise  # Пробрасываем CancelledError выше
                except Exception as e:
                    self.error_count += 1
                    logger.error(f"[ERROR] Error in polling loop ({self.error_count}/{self.max_errors}): {e}")

                    # При превышении лимита показываем stack trace
                    if self.error_count >= self.max_errors:
                        import traceback
                        logger.error(traceback.format_exc())

                # Вычисляем интервал: экспоненциальный backoff при ошибках
                if self.error_count > 0:
                    # Интервал растет: 0.5 -> 1 -> 2 -> 4 -> 8 -> 16 -> max_interval
                    current_interval = min(poll_interval * (2 ** (self.error_count - 1)), max_interval)
                    if self.error_count % 5 == 0:  # Логируем каждую 5-ю ошибку
                        logger.warning(f"[WAIT] Increased polling interval to {current_interval}s due to errors")
                else:
                    current_interval = poll_interval

                # Ждем перед следующим запросом
                await asyncio.sleep(current_interval)

        except asyncio.CancelledError:
            logger.info(f"Polling loop cancelled for {self.channel_url}")

    async def _fetch_and_process_messages(self, retry: bool = False):
        """Получить и обработать новые сообщения"""
        try:
            url = f"{self.api_base_url}/v1/chat/messages"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }

            # VK API может требовать либо slug, либо полный URL канала.
            channel_candidates = []
            for candidate in [
                self._format_chat_channel(self.channel_url),
                self._format_channel_url(self.channel_url),
            ]:
                if candidate and candidate not in channel_candidates:
                    channel_candidates.append(candidate)

            # Timeout: 10 секунд на соединение, 30 секунд на чтение
            timeout = aiohttp.ClientTimeout(total=30, connect=10)

            async with aiohttp.ClientSession(
                connector=self._get_connector(),
                timeout=timeout
            ) as session:
                last_404_error = None

                for channel_candidate in channel_candidates:
                    params = {
                        "channel_url": channel_candidate,
                        "limit": 20  # Получаем последние 20 сообщений
                    }

                    async with session.get(url, headers=headers, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            messages = data.get("data", {}).get("chat_messages", [])

                            # Обрабатываем сообщения в обратном порядке (от старых к новым)
                            for message in reversed(messages):
                                await self._process_message(message)
                            return

                        if response.status == 401:
                            error_text = await response.text()
                            if not retry and self.api_base_url != self.PROD_API_BASE_URL:
                                logger.warning(
                                    "[VK HTTP] Unauthorized on dev API for %s, switching to prod before refresh. error=%s",
                                    self.channel_url,
                                    error_text,
                                )
                                self.api_base_url = self.PROD_API_BASE_URL
                                await self._fetch_and_process_messages(retry=True)
                                return

                            logger.warning(
                                "[REFRESH] VK Live access token rejected (401), attempting refresh. channel=%s error=%s",
                                self.channel_url,
                                error_text,
                            )
                            if await self._refresh_access_token():
                                await self._fetch_and_process_messages(retry=True)
                                return
                            raise RuntimeError("VK Live OAuth token refresh failed after 401")

                        if response.status == 403:
                            raise RuntimeError(f"Forbidden: no access to VK channel {self.channel_url}")

                        error_text = await response.text()
                        if response.status == 404:
                            # Попробуем следующий формат channel_url.
                            last_404_error = (
                                f"VK messages request failed: status=404 channel={self.channel_url} "
                                f"candidate={channel_candidate} error={error_text}"
                            )
                            continue

                        raise RuntimeError(
                            f"VK messages request failed: status={response.status} channel={self.channel_url} "
                            f"candidate={channel_candidate} error={error_text}"
                        )

                # Все candidates отдали 404 на dev API -> fallback на prod (один раз).
                if not retry and self.api_base_url != self.PROD_API_BASE_URL and last_404_error:
                    logger.warning(
                        "[VK HTTP] Chat messages returned 404 on dev API for %s, switching to prod.",
                        self.channel_url,
                    )
                    self.api_base_url = self.PROD_API_BASE_URL
                    await self._fetch_and_process_messages(retry=True)
                    return

                if last_404_error:
                    # For chat polling, VK may return 404 when chat endpoint is temporarily unavailable
                    # (e.g. stream is offline or chat not initialized yet). Do not break the polling loop.
                    now_monotonic = time.monotonic()
                    if now_monotonic - self._last_chat_404_notice_monotonic >= 60:
                        logger.warning(
                            "[VK HTTP] Chat messages unavailable (404) for %s. "
                            "Polling will continue with backoff.",
                            self.channel_url,
                        )
                        self._last_chat_404_notice_monotonic = now_monotonic
                    return
                raise RuntimeError(f"VK messages request failed: no valid channel candidates for {self.channel_url}")

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if not retry and self.api_base_url != self.PROD_API_BASE_URL:
                logger.warning(f"[VK HTTP] Error on dev API ({e}), switching to prod.")
                self.api_base_url = self.PROD_API_BASE_URL
                await self._fetch_and_process_messages(retry=True)
                return
            raise

    async def _refresh_access_token(self) -> bool:
        try:
            now_monotonic = time.monotonic()
            if now_monotonic - self._last_refresh_attempt_monotonic < self.refresh_cooldown_seconds:
                logger.warning(
                    "[REFRESH] VK token refresh skipped by cooldown (%ss)",
                    self.refresh_cooldown_seconds,
                )
                return False

            self._last_refresh_attempt_monotonic = now_monotonic

            if self.token_refresh_mode == "bot":
                from services.vk_bot_oauth_service import vk_bot_oauth_service

                refreshed = await vk_bot_oauth_service.refresh_bot_token()
                if not refreshed:
                    return False

                latest_token = await vk_bot_oauth_service.get_bot_token()
                latest_access_token = latest_token.get("access_token") if latest_token else None
                if not latest_access_token:
                    return False

                self.access_token = latest_access_token
                logger.info("[REFRESH] VK bot OAuth token refreshed for polling")
                return True

            if self.token_refresh_mode != "user" or not self.user_id:
                return False

            from services.token_refresh_service import token_refresh_service
            from repositories.user_token_repository import UserTokenRepository
            from core.database import get_db
            from core.token_encryption import decrypt_token, is_token_encrypted

            refreshed = await token_refresh_service.refresh_on_401(self.user_id, 'vk')
            if not refreshed:
                return False

            db = next(get_db())
            try:
                repo = UserTokenRepository(db)
                token = repo.get_by_user_and_platform(self.user_id, 'vk')
                if not token or not token.access_token:
                    return False
                access_token = token.access_token
                if is_token_encrypted(access_token):
                    access_token = decrypt_token(access_token)
                self.access_token = access_token
                return True
            finally:
                db.close()
        except Exception as e:
            logger.error(f"[REFRESH] Failed to refresh VK token: {e}")
            return False

    async def _process_message(self, message: Dict):
        """Обработать одно сообщение"""
        try:
            message_id = message.get("id")
            created_at = message.get("created_at", 0)

            # ВАЖНО: Инициализируем last_message_time при первом запуске
            if self.last_message_time == 0:
                # Получаем текущее время в секундах (VK использует Unix timestamp)
                import time
                self.last_message_time = int(time.time()) - 10  # Последние 10 секунд
                logger.info(f"[INIT] Initialized polling timestamp: {self.last_message_time}")

            # Пропускаем уже обработанные сообщения
            if message_id in self.seen_message_ids:
                return

            # Пропускаем старые сообщения (до запуска бота)
            if created_at <= self.last_message_time:
                return

            # Помечаем как обработанное
            self.seen_message_ids.add(message_id)

            # Обновляем время последнего сообщения
            if created_at > self.last_message_time:
                self.last_message_time = created_at

            # Извлекаем данные автора
            author = message.get("author", {})
            author_nick = author.get("nick", "Unknown")
            author_id = author.get("id", 0)
            is_moderator = author.get("is_moderator", False)
            is_owner = author.get("is_owner", False)

            # Извлекаем текст сообщения + эмоты
            parts = normalize_parts(message.get("parts", []), message.get("data"))
            message_text, emotes = build_message_text_and_emotes(parts)
            badges = extract_vk_badge_urls(author)
            mentioned_users = extract_vk_mentioned_users(parts, message.get("data"), message_text)
            reply_metadata = extract_vk_reply_metadata(message)
            emotes = await self._enrich_vk_text_emotes(message_text, emotes)

            # [OK] НЕ пропускаем сообщения, даже если текст пустой - возможно это только ссылка или эмодзи
            # Проверяем наличие хотя бы одного part
            if not message_text and not parts:
                return  # Пропускаем только если вообще нет parts

            # Формируем объект сообщения для обработчика
            processed_message = {
                "id": message_id,
                "author": {
                    "nick": author_nick,
                    "id": author_id,
                    "is_moderator": is_moderator,
                    "is_owner": is_owner
                },
                "text": message_text,
                "created_at": created_at,
                "channel": self.channel_url,
                "platform": "vk",
                "badges": badges,
                "emotes": emotes or None,
                "is_reply": bool(reply_metadata.get("is_reply")),
                "mentioned_users": mentioned_users or None,
                "reply_to_author": reply_metadata.get("reply_to_author"),
                "reply_to_text": reply_metadata.get("reply_to_text"),
            }

            # Отправляем в обработчик
            if self.message_handler:
                logger.debug(f"[MSG] [VK HTTP] {author_nick}: {message_text}")
                await self.message_handler(processed_message)

        except Exception as e:
            logger.error(f"Error processing VK message: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def _enrich_vk_text_emotes(self, message_text: str, emotes: Optional[list]) -> Optional[list]:
        """
        Fallback for VK messages that arrive as plain text tokens like :lasqaJoyge:
        without smile URLs in parts/data payload.
        """
        emotes_list = list(emotes or [])
        if not isinstance(message_text, str) or not message_text:
            return emotes_list or None

        # Build a quick lookup for already mapped emotes by position.
        occupied_ranges = {(e.get("start"), e.get("end")) for e in emotes_list if isinstance(e, dict)}

        smile_map = await self._get_smile_map()
        if not smile_map:
            return emotes_list or None

        for match in re.finditer(r":([A-Za-z0-9_]+):", message_text):
            token = match.group(1)
            key = token.lower()
            smile = smile_map.get(key)
            if not smile:
                continue

            start = match.start()
            end = match.end() - 1
            if (start, end) in occupied_ranges:
                continue

            url = smile.get("url")
            if not url:
                continue

            emotes_list.append({
                "id": smile.get("id") or token,
                "name": smile.get("name") or token,
                "url": url,
                "start": start,
                "end": end,
            })
            occupied_ranges.add((start, end))

        return emotes_list or None

    async def _get_smile_map(self) -> Dict[str, Dict]:
        now = time.monotonic()
        if self._smile_map and (now - self._smile_map_updated_at) < self._smile_map_ttl_seconds:
            return self._smile_map

        channel_slug = extract_vk_channel_slug(self.channel_url)
        if not channel_slug:
            return self._smile_map

        url = f"{self.api_base_url}/v1/blog/{channel_slug}/smile/user_set/"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        params = {"mode": "public_video_stream"}

        try:
            async with aiohttp.ClientSession(connector=self._get_connector()) as session:
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status != 200:
                        return self._smile_map

                    payload = await response.json()
        except Exception:
            return self._smile_map

        candidates = []
        if isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, dict):
                for key in ("smiles", "items", "list"):
                    if isinstance(data.get(key), list):
                        candidates = data.get(key) or []
                        break
                if not candidates and isinstance(data.get("smile_user_set"), list):
                    candidates = data.get("smile_user_set") or []
            elif isinstance(data, list):
                candidates = data

            if not candidates:
                for key in ("smiles", "items", "list"):
                    if isinstance(payload.get(key), list):
                        candidates = payload.get(key) or []
                        break

        smile_map: Dict[str, Dict] = {}
        for item in candidates:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("baseName")
            if not name:
                continue
            url = (
                item.get("largeUrl")
                or item.get("large_url")
                or item.get("mediumUrl")
                or item.get("medium_url")
                or item.get("smallUrl")
                or item.get("small_url")
                or item.get("url")
            )
            if not url:
                continue
            smile_map[str(name).lower()] = {
                "id": item.get("id") or item.get("uuid") or name,
                "name": name,
                "url": url,
            }

        if smile_map:
            self._smile_map = smile_map
            self._smile_map_updated_at = now

        return self._smile_map

    async def send_message(self, text: str) -> bool:
        """Отправить сообщение в чат"""
        try:
            url = f"{self.api_base_url}/v1/chat/message/send"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            params = {
                "channel_url": self._format_channel_url(self.channel_url)
            }
            body = {
                "parts": [
                    {
                        "text": {
                            "content": text
                        }
                    }
                ]
            }

            async with aiohttp.ClientSession(connector=self._get_connector()) as session:
                async with session.post(url, headers=headers, params=params, json=body) as response:
                    if response.status == 200:
                        logger.info(f"[OK] VK message sent: {text}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"[ERROR] Failed to send VK message: {response.status} - {error_text}")
                        return False

        except Exception as e:
            logger.error(f"Error sending VK message: {e}")
            return False

