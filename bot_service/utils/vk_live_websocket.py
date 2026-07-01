# bot_service/vk_live_websocket.py
import asyncio
import json
import aiohttp
import websockets
import os
from typing import Dict, Optional, Callable
import structlog

from utils.vk_chat_parser import (
    build_message_text_and_emotes,
    extract_vk_badge_urls,
    extract_vk_mentioned_users,
    extract_vk_reply_metadata,
    normalize_parts,
)

logger = structlog.get_logger(__name__)
_VK_INSECURE_SSL = os.getenv("VK_INSECURE_SSL", "false").strip().lower() in {"1", "true", "yes", "on"}

class VKLiveWebSocketClient:
    """
    WebSocket клиент для VK Live API через Centrifugo
    
    Улучшения:
    - Exponential backoff для reconnection
    - Subscription tokens для приватных каналов
    - Улучшенная обработка ошибок
    - Интеграция с VKLiveAPIClient
    """

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.websocket = None
        self.is_connected = False
        self.subscribed_channels = set()
        self.message_handlers: Dict[str, Callable] = {}
        
        # Exponential backoff параметры
        self.reconnect_delay = 1  # Начальная задержка (секунды)
        self.max_reconnect_delay = 60  # Максимальная задержка (секунды)
        self.reconnect_attempts = 0
        
        # VKLiveAPIClient для получения subscription tokens
        self._api_client = None

    async def connect(self) -> bool:
        """
        Подключение к VK Live WebSocket с exponential backoff
        
        Returns:
            bool: True если подключение успешно
        """
        try:
            # НОВЫЙ ПОДХОД: Подключаемся БЕЗ JWT токена к ПУБЛИЧНОМУ каналу!
            # Публичные каналы VK Live НЕ требуют авторизации
            ws_url = "wss://pubsub-dev.live.vkvideo.ru/connection/websocket?format=json&cf_protocol_version=v2"

            logger.info(
                "vk_websocket_connecting",
                url=ws_url,
                attempt=self.reconnect_attempts + 1
            )
            
            self.websocket = await websockets.connect(ws_url)
            self.is_connected = True
            
            # Сбрасываем счетчик попыток при успешном подключении
            self.reconnect_attempts = 0
            self.reconnect_delay = 1
            
            logger.info("vk_websocket_connected")

            # Ждем приветственное сообщение от Centrifugo
            try:
                welcome_msg = await asyncio.wait_for(self.websocket.recv(), timeout=3.0)
                logger.debug("vk_websocket_welcome", message=welcome_msg)
            except asyncio.TimeoutError:
                logger.debug("vk_websocket_no_welcome")
            except Exception as e:
                logger.debug("vk_websocket_welcome_error", error=str(e))

            return True

        except Exception as e:
            logger.error(
                "vk_websocket_connect_failed",
                error=str(e),
                attempt=self.reconnect_attempts + 1
            )
            return False
    
    async def connect_with_retry(self, max_attempts: int = 5) -> bool:
        """
        Подключение с exponential backoff
        
        Args:
            max_attempts: Максимальное количество попыток (0 = бесконечно)
            
        Returns:
            bool: True если подключение успешно
        """
        attempt = 0
        
        while max_attempts == 0 or attempt < max_attempts:
            attempt += 1
            self.reconnect_attempts = attempt
            
            if await self.connect():
                return True
            
            # Exponential backoff
            delay = min(self.reconnect_delay * (2 ** (attempt - 1)), self.max_reconnect_delay)
            
            logger.info(
                "vk_websocket_retry",
                attempt=attempt,
                max_attempts=max_attempts if max_attempts > 0 else "unlimited",
                delay=delay
            )
            
            await asyncio.sleep(delay)
        
        logger.error(
            "vk_websocket_max_attempts_reached",
            attempts=attempt
        )
        return False

    async def _get_websocket_token(self) -> Optional[str]:
        """Получение JWT токена для WebSocket подключения"""
        try:
            # Используем dev API (только он доступен)
            endpoints = [
                "https://apidev.live.vkvideo.ru/v1/websocket/token",
                "https://api.vk.com/method/streaming.getServerUrl"
            ]

            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }

            # SSL config: secure by default, optional insecure dev fallback.
            import ssl
            ssl_context = ssl.create_default_context()
            if _VK_INSECURE_SSL:
                logger.warning("vk_websocket_ssl_insecure_mode_enabled")
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
                for url in endpoints:
                    try:
                        logger.info(f"Trying VK API endpoint: {url}")
                        async with session.get(url, headers=headers) as response:
                            if response.status == 200:
                                data = await response.json()
                                token = data.get("data", {}).get("token") or data.get("response", {}).get("endpoint")
                                if token:
                                    logger.info(f"[OK] Got token from {url}")
                                    return token
                            else:
                                try:
                                    body = await response.text()
                                except Exception:
                                    body = "<no body>"
                                logger.warning(f"Endpoint {url} returned {response.status}: {body}")
                    except Exception as e:
                        logger.warning(f"Error with endpoint {url}: {e}")
                        continue

            # Если все endpoints не работают, попробуем без токена
            logger.warning("All VK API endpoints failed, trying without token")
            return None

        except Exception as e:
            logger.error(f"Error getting WebSocket token: {e}")
            return None

    async def subscribe_to_channel(self, channel_name: str, use_subscription_token: bool = True) -> bool:
        """
        Подписка на канал чата
        
        Args:
            channel_name: Имя канала (из VK API)
            use_subscription_token: Использовать subscription token для приватных каналов
            
        Returns:
            bool: True если подписка успешна
        """
        try:
            if not self.is_connected or not self.websocket:
                logger.error("vk_websocket_not_connected")
                return False

            logger.info(
                "vk_websocket_subscribing",
                channel=channel_name,
                use_token=use_subscription_token
            )

            # Получаем subscription token если нужно
            subscription_token = None
            if use_subscription_token:
                subscription_token = await self._get_subscription_token_for_channel(channel_name)
                if subscription_token:
                    logger.info(
                        "vk_websocket_got_subscription_token",
                        channel=channel_name
                    )

            # Формируем subscribe команду
            subscribe_msg = {
                "id": 1,
                "method": "subscribe",
                "params": {
                    "channel": channel_name
                }
            }
            
            # Добавляем token если есть
            if subscription_token:
                subscribe_msg["params"]["token"] = subscription_token

            logger.debug(
                "vk_websocket_sending_subscribe",
                message=subscribe_msg
            )
            
            await self.websocket.send(json.dumps(subscribe_msg))

            try:
                # Ждем подтверждения подписки
                response = await asyncio.wait_for(self.websocket.recv(), timeout=10.0)
                logger.debug(
                    "vk_websocket_subscription_response",
                    response=response
                )

                # Парсим ответ подписки
                try:
                    response_data = json.loads(response)
                    if "result" in response_data and response_data.get("result") is not False:
                        self.subscribed_channels.add(channel_name)
                        logger.info(
                            "vk_websocket_subscribed",
                            channel=channel_name
                        )
                        return True
                    elif "error" in response_data:
                        error = response_data.get("error", {})
                        logger.error(
                            "vk_websocket_subscription_error",
                            channel=channel_name,
                            error_code=error.get("code"),
                            error_message=error.get("message")
                        )
                        return False
                    else:
                        logger.warning(
                            "vk_websocket_unexpected_response",
                            response=response_data
                        )
                        return False
                except json.JSONDecodeError:
                    logger.error(
                        "vk_websocket_invalid_response",
                        response=response
                    )
                    return False

            except asyncio.TimeoutError:
                logger.error(
                    "vk_websocket_subscription_timeout",
                    channel=channel_name
                )
                return False

        except Exception as e:
            logger.error(
                "vk_websocket_subscribe_failed",
                channel=channel_name,
                error=str(e)
            )
            return False

    async def _get_subscription_token_for_channel(self, channel_name: str) -> Optional[str]:
        """
        Получить subscription token для приватного канала
        
        Использует VKLiveAPIClient для получения токена
        
        Args:
            channel_name: Имя канала
            
        Returns:
            Optional[str]: Subscription token или None
        """
        try:
            # Используем VKLiveAPIClient если доступен
            if self._api_client is None:
                from utils.vk_api_client import VKLiveAPIClient
                self._api_client = VKLiveAPIClient()
            
            # Получаем subscription tokens для канала
            tokens = await self._api_client.get_subscription_tokens(
                token=self.access_token,
                channels=[channel_name]
            )
            
            if channel_name in tokens:
                logger.info(
                    "vk_websocket_got_subscription_token",
                    channel=channel_name
                )
                return tokens[channel_name]
            
            logger.warning(
                "vk_websocket_no_subscription_token",
                channel=channel_name
            )
            return None

        except Exception as e:
            logger.warning(
                "vk_websocket_subscription_token_error",
                channel=channel_name,
                error=str(e)
            )
            return None

    async def receive_message(self) -> Optional[Dict]:
        """Получить одно сообщение из WebSocket"""
        try:
            if not self.is_connected or not self.websocket:
                return None

            # Получаем сырое сообщение
            raw_message = await asyncio.wait_for(self.websocket.recv(), timeout=0.1)

            # Парсим JSON
            data = json.loads(raw_message)

            # Обрабатываем публикации (новые сообщения чата)
            if data.get("method") == "publication":
                params = data.get("params", {})
                message_data = params.get("data", {})

                # Возвращаем сообщение чата в формате для обработки
                return message_data

            return None

        except asyncio.TimeoutError:
            # Нет сообщений - это норма
            return None
        except websockets.exceptions.ConnectionClosed:
            logger.info("VK Live WebSocket connection closed")
            self.is_connected = False
            return None
        except Exception as e:
            logger.debug(f"Error receiving message: {e}")
            return None

    async def listen_for_messages(self, auto_reconnect: bool = True):
        """
        Прослушивание сообщений из WebSocket с auto-reconnect
        
        Args:
            auto_reconnect: Автоматически переподключаться при разрыве соединения
        """
        while True:
            try:
                if not self.is_connected:
                    if auto_reconnect:
                        logger.info("vk_websocket_reconnecting")
                        if not await self.connect_with_retry(max_attempts=5):
                            logger.error("vk_websocket_reconnect_failed")
                            break
                        
                        # Переподписываемся на все каналы
                        channels_to_resubscribe = list(self.subscribed_channels)
                        self.subscribed_channels.clear()
                        
                        for channel in channels_to_resubscribe:
                            await self.subscribe_to_channel(channel)
                    else:
                        break
                
                message = await self.websocket.recv()
                await self._handle_message(message)

            except websockets.exceptions.ConnectionClosed:
                logger.info("vk_websocket_connection_closed")
                self.is_connected = False
                
                if not auto_reconnect:
                    break
                    
                # Exponential backoff перед reconnect
                delay = min(
                    self.reconnect_delay * (2 ** self.reconnect_attempts),
                    self.max_reconnect_delay
                )
                logger.info(
                    "vk_websocket_reconnect_delay",
                    delay=delay,
                    attempt=self.reconnect_attempts + 1
                )
                await asyncio.sleep(delay)
                
            except Exception as e:
                logger.error(
                    "vk_websocket_listen_error",
                    error=str(e)
                )
                self.is_connected = False
                
                if not auto_reconnect:
                    break
                    
                await asyncio.sleep(5)

    async def _handle_message(self, message: str):
        """Обработка входящих сообщений"""
        try:
            data = json.loads(message)

            # Обрабатываем разные типы сообщений Centrifugo
            if "result" in data:
                # Ответ на команду (connect, subscribe)
                logger.debug(f"VK Live WebSocket response: {data}")
            elif "method" in data:
                method = data["method"]
                if method == "message":
                    # Сообщение из канала
                    await self._handle_channel_message(data)
                elif method == "publication":
                    # Публикация в канале (новое сообщение)
                    await self._handle_publication(data)
                else:
                    logger.debug(f"VK Live WebSocket method {method}: {data}")
            else:
                logger.debug(f"VK Live WebSocket message: {data}")

        except json.JSONDecodeError:
            logger.error(f"Failed to parse WebSocket message: {message}")
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}")

    async def _handle_publication(self, data: dict):
        """Обработка публикации в канале (новое сообщение)"""
        try:
            channel = data.get("params", {}).get("channel", "")
            message_data = data.get("params", {}).get("data", {})

            logger.info(f"[BROADCAST] VK Live publication in {channel}: {message_data}")

            # Обрабатываем как сообщение чата
            await self._handle_chat_message(channel, message_data)

        except Exception as e:
            logger.error(f"Error handling publication: {e}")

    async def _handle_channel_message(self, data: dict):
        """Обработка сообщения из канала чата"""
        try:
            channel = data.get("params", {}).get("channel", "")
            message_data = data.get("params", {}).get("data", {})

            # Извлекаем информацию о сообщении
            message_type = message_data.get("type")

            if message_type == "chat_message":
                # Новое сообщение в чате
                await self._handle_chat_message(channel, message_data)
            elif message_type == "user_joined":
                # Пользователь присоединился к чату
                logger.info(f"User joined chat: {message_data}")
            elif message_type == "user_left":
                # Пользователь покинул чат
                logger.info(f"User left chat: {message_data}")
            else:
                logger.debug(f"Unknown message type: {message_type}")

        except Exception as e:
            logger.error(f"Error handling channel message: {e}")

    async def _handle_chat_message(self, channel: str, message_data: dict):
        """Обработка сообщения чата"""
        try:
            chat_payload = message_data
            if isinstance(message_data, dict):
                nested_payload = message_data.get("chat_message") or message_data.get("message")
                if isinstance(nested_payload, dict):
                    chat_payload = nested_payload

            # Извлекаем данные сообщения
            author = chat_payload.get("author", {})
            message_id = chat_payload.get("id")
            created_at = chat_payload.get("created_at")
            parts = normalize_parts(chat_payload.get("parts", []), chat_payload.get("data"))

            # Формируем текст сообщения
            message_text, emotes = build_message_text_and_emotes(parts)
            mentioned_users = extract_vk_mentioned_users(parts, chat_payload.get("data"), message_text)
            reply_metadata = extract_vk_reply_metadata(chat_payload)

            # Извлекаем информацию об авторе
            author_id = author.get("id")
            author_nick = author.get("nick", "Unknown")
            is_moderator = author.get("is_moderator", False)
            is_owner = author.get("is_owner", False)
            badges = extract_vk_badge_urls(author)

            # Логируем сообщение
            logger.info(f"VK Live chat message from {author_nick} ({author_id}): {message_text}")

            # Вызываем обработчик сообщения, если он зарегистрирован
            if channel in self.message_handlers:
                await self.message_handlers[channel]({
                    "channel": channel,
                    "author_id": author_id,
                    "author_nick": author_nick,
                    "message": message_text,
                    "is_moderator": is_moderator,
                    "is_owner": is_owner,
                    "message_id": message_id,
                    "created_at": created_at,
                    "badges": badges,
                    "emotes": emotes or None,
                    "is_reply": bool(reply_metadata.get("is_reply")),
                    "mentioned_users": mentioned_users or None,
                    "reply_to_author": reply_metadata.get("reply_to_author"),
                    "reply_to_text": reply_metadata.get("reply_to_text"),
                })

        except Exception as e:
            logger.error(f"Error handling chat message: {e}")

    def register_message_handler(self, channel: str, handler: Callable):
        """Регистрация обработчика сообщений для канала"""
        self.message_handlers[channel] = handler

    async def disconnect(self):
        """Отключение от WebSocket"""
        try:
            self.is_connected = False
            if self.websocket:
                await self.websocket.close()
                self.websocket = None
            
            # Закрываем API client если был создан
            if self._api_client:
                await self._api_client.close()
                self._api_client = None
            
            logger.info("vk_websocket_disconnected")
        except Exception as e:
            logger.error(
                "vk_websocket_disconnect_error",
                error=str(e)
            )
