# bot_service/bots/vk_live_bot.py
"""Главный файл VK Live бота"""
import logging
import os
from core.connection_manager import ConnectionManager
from .vk_live_bot_core import VKLiveBotCore

logger = logging.getLogger('bot_service')
_VK_INSECURE_SSL = os.getenv("VK_INSECURE_SSL", "false").strip().lower() in {"1", "true", "yes", "on"}

class VKLiveBot(VKLiveBotCore):
    """Главный класс VK Live бота"""

    def __init__(self, user_access_token: str, connection_manager: ConnectionManager):
        super().__init__(user_access_token, connection_manager)
        logger.info("[VK BOT] VK Live bot initialized")

    async def start_bot(self):
        """Запуск VK Live бота"""
        await super().start_bot()
        logger.info("[VK BOT] All modules loaded and ready!")

    async def stop_bot(self):
        """Остановка VK Live бота"""
        await super().stop_bot()
        logger.info("[VK BOT] VK Live bot shutdown complete")

    async def connect_to_channel(self, channel_id: str) -> bool:
        """Подключиться к каналу VK Live"""
        success = await super().connect_to_channel(channel_id)

        if success:
            # Уведомляем connection_manager
            self.connection_manager.add_active_session(
                channel_id,
                f"vk_{channel_id}",
                "vk"
            )

            # Note: VK Live API не поддерживает отправку сообщений от бота в чат
            # Можно логировать подключение, но нельзя отправить welcome message
            import random
            fake_ip = f"{random.randint(100, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}"
            logger.info(f"[OK] [VK BOT] Connected to {channel_id} (fake IP for fun: {fake_ip})")

        return success

    async def disconnect_from_channel(self, channel_id: str) -> bool:
        """Отключиться от канала VK Live"""
        success = await super().disconnect_from_channel(channel_id)

        if success:
            # Уведомляем connection_manager
            self.connection_manager.remove_active_session(
                channel_id,
                "vk_disconnect"
            )

        return success

    async def send_message(self, channel_id: str, message: str) -> bool:
        """Отправить сообщение в канал VK Live (используя HTTP Bot Token)"""
        try:
            if not self.is_connected_to_channel(channel_id):
                logger.error(f"Not connected to channel {channel_id}")
                return False

            # Прямая отправка через HTTP API используя токен БОТА (self.user_access_token)
            import aiohttp
            from utils.vk_channel_url import extract_vk_channel_slug
            
            # channel_id usually comes as slug (e.g. "yourchy"), but we ensure it
            slug = extract_vk_channel_slug(channel_id) or channel_id
            
            url = "https://api.live.vkvideo.ru/v1/chat/message/send"
            
            headers = {
                "Authorization": f"Bearer {self.user_access_token}",
                "Content-Type": "application/json"
            }
            
            # Use query param for channel_url
            params = {
                "channel_url": f"https://live.vkvideo.ru/{slug}"
            }
            
            json_body = {
                "parts": [
                    {
                        "text": {
                            "content": message
                        }
                    }
                ]
            }

            # SSL config: secure by default, optional insecure dev fallback.
            import ssl
            ssl_context = ssl.create_default_context()
            if _VK_INSECURE_SSL:
                logger.warning("[VK BOT] SSL verification disabled via VK_INSECURE_SSL=true")
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
                async with session.post(url, headers=headers, params=params, json=json_body) as response:
                    if response.status == 200:
                        logger.info(f"[VK BOT] Message sent to {slug}: {message}")
                        return True
                    else:
                        text = await response.text()
                        logger.error(f"[VK BOT] Failed to send message: {response.status} - {text}")
                        
                        # Fallback to DEV API only when production does not know the endpoint/channel.
                        if response.status == 404:
                            dev_url = "https://apidev.live.vkvideo.ru/v1/chat/message/send"
                            async with session.post(dev_url, headers=headers, params=params, json=json_body) as dev_resp:
                                if dev_resp.status == 200:
                                    logger.info(f"[VK BOT] Message sent to {slug} (DEV API fallback): {message}")
                                    return True
                                else:
                                    dev_text = await dev_resp.text()
                                    logger.error(f"[VK BOT] DEV API fallback failed: {dev_resp.status} - {dev_text}")
                                    return False
                        return False

        except Exception as e:
            logger.error(f"Error sending VK Live message: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def shutdown(self):
        """Корректное завершение работы бота"""
        try:
            logger.info("[VK BOT] Shutting down VK Live bot...")

            # Отключаемся от всех каналов
            for channel_id in self.connected_channels.copy():
                await self.disconnect_from_channel(channel_id)

            await self.stop_bot()
            logger.info("[VK BOT] VK Live bot shutdown complete")
        except Exception as e:
            logger.error(f"[VK BOT] Error during bot shutdown: {e}")
