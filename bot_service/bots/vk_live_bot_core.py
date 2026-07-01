# bot_service/bots/vk_live_bot_core.py
"""Основной класс VK Live бота"""
import asyncio
import logging
import os
from typing import List, Dict, Any, Optional
from core.connection_manager import ConnectionManager
from utils.vk_live_websocket import VKLiveWebSocketClient
from utils.vk_channel_url import normalize_vk_channel_url
from services.youtube.reward_settings import get_platform_reward_configuration

logger = logging.getLogger('bot_service')
_VK_INSECURE_SSL = os.getenv("VK_INSECURE_SSL", "false").strip().lower() in {"1", "true", "yes", "on"}

class VKLiveBotCore:
    """Основной класс VK Live бота
    
    IMPORTANT: user_access_token - это OAuth токен БОТА,
    полученный через /auth/vk/bot/login и сохраненный в bot_tokens.
    
    Это НЕ токен стримера! Аналогично Twitch Bot Token.
    """

    def __init__(self, user_access_token: str, connection_manager: ConnectionManager):
        """
        Args:
            user_access_token: OAuth токен БОТА для работы в чате
            connection_manager: Менеджер соединений
        """
        self.user_access_token = user_access_token  # Токен БОТА для чата
        self.connection_manager = connection_manager
        self.connected_channels: List[str] = []
        self.is_running = False

        self.ws_client: Optional[VKLiveWebSocketClient] = None
        self.ws_task: Optional[asyncio.Task] = None

        # Инициализируем TTS API для обработки сообщений
        from services.tts.tts_core import TTSAPI
        self.tts_api = TTSAPI()

        # Универсальная система команд
        from bots.universal_command_handler import UniversalCommandHandler
        self.universal_command_handler = UniversalCommandHandler()

    async def start_bot(self):
        """Запуск VK Live бота"""
        if self.is_running:
            logger.warning("VK Live bot is already running")
            return

        self.is_running = True
        logger.info("[START] VK LIVE BOT STARTED - Ready to listen to chat")
        logger.info("VK LIVE BOT: Started and ready to connect to channels")

    async def stop_bot(self):
        """Остановка VK Live бота"""
        if not self.is_running:
            logger.warning("VK Live bot is not running")
            return

        self.is_running = False
        logger.info(" VK LIVE BOT STOPPED")

    async def connect_to_channel(self, channel_id: str) -> bool:
        """Подключиться к каналу VK Live (используя HTTP polling вместо WebSocket)"""
        try:
            if channel_id in self.connected_channels:
                logger.warning(f"Already connected to channel {channel_id}")
                return True

            # Use HTTP polling for chat reads.
            from utils.vk_live_http_polling import VKLiveHTTPPolling
            from core.database import get_db

            logger.info(f"[CONNECT] Connecting VK Live HTTP polling to channel: {channel_id}")

            resolved_channel = channel_id
            owner_user_id: Optional[int] = None

            db = next(get_db())
            try:
                from repositories.user_repository import UserRepository
                user_repo = UserRepository(db)
                user = user_repo.get_by_vk_channel_name(channel_id) or user_repo.get_by_vk_username(channel_id)
                if user:
                    owner_user_id = user.id
                    preferred_channel = user.vk_channel_name or user.vk_username
                    if preferred_channel:
                        resolved_channel = preferred_channel
                else:
                    logger.warning(f"[WARN] User not found for VK channel '{channel_id}', using raw slug")

            finally:
                db.close()

            # Validate resolved channel slug (must be a URL slug, not display name).
            # Keep original case because some VK identifiers can be case-sensitive.
            resolved_channel = resolved_channel.strip()
            if not resolved_channel or ' ' in resolved_channel:
                logger.warning(f"[WARN] VK channel slug invalid for polling: '{resolved_channel}'. Skipping polling.")
                return False

            # Polling always uses dedicated bot token (same model as Twitch bot).
            self.http_polling = VKLiveHTTPPolling(
                access_token=self.user_access_token,
                channel_url=resolved_channel,
                user_id=owner_user_id,
                token_refresh_mode="bot"
            )

            # Запускаем polling с обработчиком сообщений
            await self.http_polling.start(self._handle_message)

            self.connected_channels.append(channel_id)
            logger.info(f"[OK] VK Live HTTP polling started for channel: {channel_id}")

            return True

        except Exception as e:
            logger.error(f"[ERROR] Failed to connect to channel {channel_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def _get_websocket_channel_name(self, channel_url: str) -> str:
        """Получить реальное имя WebSocket канала из VK API"""
        try:
            import aiohttp

            url = "https://apidev.live.vkvideo.ru/v1/channel"
            headers = {
                "Authorization": f"Bearer {self.user_access_token}",
                "Content-Type": "application/json"
            }
            params = {
                "channel_url": normalize_vk_channel_url(channel_url)
            }

            # SSL config: secure by default, optional insecure dev fallback.
            import ssl
            ssl_context = ssl.create_default_context()
            if _VK_INSECURE_SSL:
                logger.warning("[VK BOT] SSL verification disabled via VK_INSECURE_SSL=true")
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        ws_channels = data.get("data", {}).get("channel", {}).get("web_socket_channels", {})

                        # Логируем ВСЕ доступные каналы
                        logger.info(f"[LIST] Available WebSocket channels: {ws_channels}")

                        # Пробуем разные варианты каналов в порядке приоритета:
                        # 1. chat - ПОСТОЯННЫЙ публичный чат канала (работает всегда)
                        # 2. limited_chat - приватный чат ТЕКУЩЕГО стрима (только во время стрима)
                        # 3. private_chat - личный чат

                        for channel_type in ["chat", "limited_chat", "private_chat"]:
                            chat_channel = ws_channels.get(channel_type)
                            if chat_channel:
                                logger.info(f"[OK] Selected WebSocket channel ({channel_type}): {chat_channel}")
                                return chat_channel

                        logger.error(f"[ERROR] No chat channel found in response for {channel_url}")
                        return None
                    else:
                        error_text = await response.text()
                        logger.error(f"[ERROR] Failed to get channel info: {response.status} - {error_text}")
                        return None

        except Exception as e:
            logger.error(f"Error getting WebSocket channel name: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    async def disconnect_from_channel(self, channel_id: str) -> bool:
        """Отключиться от канала VK Live"""
        try:
            if channel_id not in self.connected_channels:
                logger.warning(f"Not connected to channel {channel_id}")
                return True

            # Останавливаем HTTP polling
            if hasattr(self, 'http_polling') and self.http_polling:
                await self.http_polling.stop()
                self.http_polling = None

            self.connected_channels.remove(channel_id)
            logger.info(f"[OK] Disconnected from VK Live channel: {channel_id}")

            return True

        except Exception as e:
            logger.error(f"[ERROR] Failed to disconnect from channel {channel_id}: {e}")
            return False

    async def _read_messages(self):
        """Чтение сообщений из WebSocket"""
        try:
            while self.is_running and self.ws_client:
                message = await self.ws_client.receive_message()
                if message:
                    await self._handle_message(message)
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            logger.info("Message reading task cancelled")
        except Exception as e:
            logger.error(f"Error reading messages: {e}")
            # Fallback: если WebSocket не работает, пробуем polling
            logger.info("[REFRESH] Falling back to VK Live polling mode")
            await self._poll_vk_live_messages()

    async def _handle_message(self, message: Dict[str, Any]):
        """Обработка входящего сообщения"""
        try:
            # Логируем все сообщения
            text = message.get("text", "")
            source_message_id = str(message.get("id") or message.get("message_id") or "").strip() or None
            author = message.get("author", {})
            user = author.get("nick", author.get("name", "Unknown"))  # nick - правильное поле для VK Live
            user_id = str(author.get("id", ""))
            channel_id = message.get("channel", "")  # HTTP polling передает channel в этом поле
            message.get("platform", "vk")
            is_owner = author.get("is_owner", False) or author.get("is_broadcaster", False)
            is_moderator = author.get("is_moderator", False)
            badges = message.get("badges")
            emotes = message.get("emotes")
            is_reply = bool(message.get("is_reply"))
            mentioned_users = message.get("mentioned_users") or []
            avatar_url = (
                author.get("avatar_url")
                or author.get("avatar")
                or author.get("photo")
                or author.get("photo_url")
            )

            # Определяем роль для VK Live
            role = None
            if is_owner:
                role = 'broadcaster'
            elif is_moderator:
                role = 'moderator'

            logger.debug(f"[VK MSG] {channel_id} | {user} (owner={is_owner}, mod={is_moderator}, role={role}): {text[:50]}")

            # 1. Отправляем сообщение в WebSocket для отображения в chatbox
            from utils.websocket_helper import broadcast_chat_message
            await broadcast_chat_message(
                username=user,
                content=text,
                platform="vk",
                channel=channel_id,
                message_id=source_message_id,
                role=role,
                badges=badges,
                emotes=emotes,
                avatar_url=avatar_url
            )

            # 1.5. [OK] НОВОЕ: Увеличиваем счетчик сообщений для стриков (только если стрик включен)
            try:
                from services.drops.drops_service import DropsService
                from core.database import get_db
                from repositories.user_repository import UserRepository

                db = get_db().__next__()
                try:
                    user_repo = UserRepository(db)
                    channel_owner = user_repo.get_by_vk_channel_name(channel_id)

                    if channel_owner:
                        drops_service = DropsService(db)
                        # [OK] Проверяем включен ли стрик для VK
                        config = drops_service.get_config(
                            user_id=channel_owner.id,
                            session_id=None,
                            channel_name=channel_id.lower(),
                            platform=None  # Общий конфиг
                        )

                        # Проверяем включен ли стрик для VK
                        streak_enabled = False
                        if config:
                            streak_enabled = getattr(config, 'streak_enabled_vk', False)

                        # Увеличиваем счетчик только если стрик включен
                        if streak_enabled:
                            drops_service.increment_viewer_message_count_for_user(
                                user_id=channel_owner.id,
                                channel_name=channel_id.lower(),
                                platform="vk",
                                viewer_id=user_id,
                                viewer_name=user
                            )

                            # [OK] Обрабатываем стрик Drops (проверяем награды)
                            try:
                                result = drops_service.process_streak_drops_for_user(
                                    user_id=channel_owner.id,
                                    channel_name=channel_id.lower(),
                                    platform="vk",
                                    viewer_id=user_id,
                                    viewer_name=user
                                )

                                if result:
                                    logger.info("[DROPS VK] %s pending streak chest: %s", result.get("viewer_name"), result.get("quality"))
                            except Exception as drops_err:
                                logger.debug(f"Could not process streak drops for VK: {drops_err}")
                finally:
                    db.close()
            except Exception as streak_err:
                logger.debug(f"Could not increment streak message count for VK: {streak_err}")

            # 3. Обрабатываем команды через универсальную систему
            if text.startswith('!'):
                logger.info(f"[GAME] [VK CMD] Detected command: {text[:50]}")
                # Преобразуем формат сообщения для universal_command_handler
                command_message = {
                    'message': text,
                    'author_nick': user,
                    'author_id': message.get("author", {}).get("id"),
                    'is_moderator': message.get("author", {}).get("is_moderator", False),
                    'is_owner': message.get("author", {}).get("is_owner", False)
                }
                logger.info(f"[GAME] [VK CMD] Calling handler for channel: {channel_id}, message: {command_message}")
                await self.universal_command_handler.handle_vk_command(channel_id, command_message, self)
                logger.info(f"[GAME] [VK CMD] Handler completed for: {text[:50]}")
                return  # Не обрабатываем TTS для команд

            await self.universal_command_handler.handle_vk_message(channel_id, {
                'message': text,
                'author_nick': user,
                'author_id': message.get("author", {}).get("id"),
                'is_moderator': message.get("author", {}).get("is_moderator", False),
                'is_owner': message.get("author", {}).get("is_owner", False)
            }, self)

            # 4. Извлекаем reward_id из сообщения
            reward_id = None
            reward_title = None

            # VK Live не передает reward_id напрямую, но ChatBot отправляет сообщения о наградах
            # Паттерн: "получает награду: [название награды] за [стоимость]"
            if user.lower() == 'chatbot':
                import re
                reward_pattern = r'получает награду:\s*([^\n]+?)\s*за\s*\d+'
                match = re.search(reward_pattern, text)
                if match:
                    reward_title = match.group(1).strip()
                    logger.info(f"[REWARD] [VK MSG] Detected reward from ChatBot: '{reward_title}'")

                    # Ищем reward_id TTS награды из настроек пользователя
                    from core.database import SessionLocal
                    from repositories.user_repository import UserRepository
                    from repositories.tts_settings_repository import TTSSettingsRepository
                    from services.memealerts_service import MemeAlertsService
                    
                    db = SessionLocal()
                    try:
                        user_repo = UserRepository(db)
                        tts_settings_repo = TTSSettingsRepository(db)
                        
                        channel_owner = user_repo.get_by_vk_channel_name(channel_id)

                        if channel_owner:
                            tts_settings = tts_settings_repo.get_or_create(user_id=channel_owner.id)
                            viewer_name = text.split('получает награду')[0].strip() if 'получает награду' in text else user
                            reward_line_pattern = r'^.*?получает награду:\s*[^\n]+?\s*за\s*\d+\s*\n*'
                            cleaned_text = re.sub(reward_line_pattern, '', text, flags=re.MULTILINE).strip()

                            memealerts_service = MemeAlertsService(db)
                            meme_reward_result = await memealerts_service.process_points_reward_redemption(
                                user_id=channel_owner.id,
                                platform='vk',
                                channel_name=channel_id,
                                redeemer_name=viewer_name,
                                reward_input=cleaned_text,
                                reward_title=reward_title,
                            )
                            if meme_reward_result.get('handled'):
                                if meme_reward_result.get('success'):
                                    await self.send_message(
                                        channel_id,
                                        f"@{viewer_name} выдано {meme_reward_result.get('amount')} мемкоинов "
                                        f"пользователю {meme_reward_result.get('nickname')}"
                                    )
                                else:
                                    await self.send_message(
                                        channel_id,
                                        f"@{viewer_name} {meme_reward_result.get('error', 'не удалось выдать мемкоины')}"
                                    )
                                return

                            # Если название награды содержит "TTS" - считаем что это TTS награда
                            if tts_settings and tts_settings.tts_reward_ids and 'tts' in reward_title.lower():
                                stored_reward_id = tts_settings.tts_reward_ids.get('vk')
                                if stored_reward_id:
                                    reward_id = stored_reward_id
                                    logger.info(f"[OK] [VK MSG] Matched TTS reward_id: {reward_id}")

                            # Обработка награды для заказа YouTube
                            youtube_settings = getattr(tts_settings, 'youtube_settings', None) or {}
                            reward_config = get_platform_reward_configuration(
                                youtube_settings,
                                platform='vk',
                            )
                            vk_reward_enabled = bool(reward_config.get('enabled'))
                            configured_reward = str(reward_config.get('reward_value') or '').strip()

                            if vk_reward_enabled:
                                if configured_reward and configured_reward.lower() == reward_title.lower():
                                    from services.youtube.queue_service import QueueService

                                    if cleaned_text:
                                        queue_service = QueueService()
                                        result = await queue_service.add_video_to_queue(
                                            user_id=channel_owner.id,
                                            video_url=cleaned_text,
                                            channel_name=channel_id,
                                            platform='vk',
                                            requester_name=viewer_name,
                                            requester_id=viewer_name,
                                            is_paid=True,
                                            db=db
                                        )
                                        if result.get('success'):
                                            await self.send_message(channel_id, f"@{viewer_name} видео добавлено: {result.get('video_info', {}).get('title', 'Video')[:40]}")
                                        else:
                                            await self.send_message(channel_id, f"@{viewer_name} ошибка добавления: {result.get('error')}")
                                        return
                    finally:
                        db.close()

            # 5. Обработка TTS для обычных сообщений
            await self._handle_vk_tts(
                message,
                channel_id,
                user,
                text,
                reward_id,
                reward_title,
                is_reply=is_reply,
                mentioned_users=mentioned_users,
            )

        except Exception as e:
            logger.error(f"Error handling VK Live message: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")

    async def _handle_vk_tts(
        self,
        message: Dict[str, Any],
        channel_id: str,
        username: str,
        text: str,
        reward_id: str = None,
        reward_title: str = None,
        *,
        is_reply: bool = False,
        mentioned_users: Optional[list[str]] = None,
    ):
        """Обработка TTS для VK сообщений"""
        from utils.websocket_helper import handle_tts_for_message

        # Если это сообщение с наградой от ChatBot - извлекаем чистый текст
        cleaned_text = text
        if username.lower() == 'chatbot' and reward_title:
            import re
            # Удаляем служебное сообщение "получает награду: [название] за [стоимость]"
            reward_pattern = r'^получает награду:\s*[^\n]+?\s*за\s*\d+\s*\n*'
            cleaned_text = re.sub(reward_pattern, '', text, flags=re.MULTILINE).strip()
            logger.info(f"[CLEANUP] [VK TTS] Cleaned text from reward message: '{cleaned_text[:50]}...'")

        await handle_tts_for_message(
            text=cleaned_text,
            username=username.lower(),
            channel_identifier=channel_id,
            platform='vk',
            tts_api=self.tts_api,
            connection_manager=self.connection_manager,
            skip_if_command=False,  # Команды уже отфильтрованы в _handle_message
            is_reply=is_reply,
            mentioned_users=mentioned_users or [],
            reward_id=reward_id,  # Передаем reward_id если есть
            message_id=str(message.get("id") or message.get("message_id") or "").strip() or None,
        )

    def get_connected_channels(self) -> List[str]:
        """Получить список подключенных каналов"""
        return self.connected_channels.copy()

    def is_connected_to_channel(self, channel_id: str) -> bool:
        """Проверить подключение к каналу"""
        return channel_id in self.connected_channels

    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику бота"""
        return {
            "is_running": self.is_running,
            "connected_channels": len(self.connected_channels),
            "channels": self.connected_channels.copy(),
            "ws_connected": self.ws_client is not None and self.ws_client.is_connected()
        }

    async def _poll_vk_live_messages(self):
        """Fallback метод для получения сообщений через polling"""
        try:
            logger.info("[REFRESH] Starting VK Live polling mode")
            import aiohttp

            while self.is_running:
                try:
                    # Получаем сообщения через VK API
                    timeout = aiohttp.ClientTimeout(total=30, connect=10)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        # Пробуем разные API endpoints
                        endpoints = [
                            f"https://api.live.vkvideo.ru/v1/streams/{channel_id}/chat/messages" for channel_id in self.connected_channels
                        ]

                        for endpoint in endpoints:
                            try:
                                headers = {
                                    "Authorization": f"Bearer {self.user_access_token}",
                                    "Content-Type": "application/json"
                                }

                                async with session.get(endpoint, headers=headers) as response:
                                    if response.status == 200:
                                        data = await response.json()
                                        messages = data.get("data", {}).get("messages", [])

                                        for message in messages:
                                            await self._handle_message(message)

                                        logger.info(f"[VK POLL] Polled {len(messages)} messages from VK Live")
                                        break
                                    else:
                                        logger.debug(f"Polling endpoint {endpoint} returned {response.status}")

                            except Exception as e:
                                logger.debug(f"Error polling {endpoint}: {e}")
                                continue

                        # Ждем перед следующим запросом
                        await asyncio.sleep(5)

                except Exception as e:
                    logger.error(f"Error in VK Live polling: {e}")
                    await asyncio.sleep(10)

        except Exception as e:
            logger.error(f"Fatal error in VK Live polling: {e}")

