# bot_service/bots/twitch_bot_core.py
"""РћСЃРЅРѕРІРЅРѕР№ РєР»Р°СЃСЃ Twitch Р±РѕС‚Р°"""
import asyncio
import logging
from typing import List, Optional
from twitchio.ext import commands
from core.connection_manager import ConnectionManager
from services.tts.tts_core import TTSAPI
from services.youtube.youtube_service import YouTubeService

# РќР°СЃС‚СЂРѕР№РєР° Р»РѕРіРёСЂРѕРІР°РЅРёСЏ РґР»СЏ TwitchIO
logging.getLogger('twitchio').setLevel(logging.INFO)
logging.getLogger('twitchio.websocket').setLevel(logging.INFO)
logging.getLogger('twitchio.client').setLevel(logging.INFO)

logger = logging.getLogger('bot_service')

class TwitchBotCore(commands.Bot):
    """РћСЃРЅРѕРІРЅРѕР№ РєР»Р°СЃСЃ Twitch Р±РѕС‚Р°"""

    def __init__(self, token: str, initial_channels: List[str], connection_manager: ConnectionManager):
        logger.info("[BOT] CREATING TWITCH BOT")
        logger.info("[INFO] Token: [CENSORED]")
        logger.info(f"[CHANNELS] Initial channels: {initial_channels}")
        logger.info(f"[DEBUG] Token length: {len(token)}")
        logger.info(f"[DEBUG] Number of channels: {len(initial_channels)}")

        self.connection_manager = connection_manager
        self.ready_event = asyncio.Event()
        self.tts_api = TTSAPI()
        # self.youtube_api is deprecated, use services.youtube.youtube_service if needed
        # Initializing service here if needed, or in specific handlers
        from services.youtube.youtube_service import YouTubeService
        self.youtube_service = YouTubeService()

        logger.info("[WRENCH] Initializing TwitchIO Bot...")
        logger.info(f"[DEBUG] Calling super().__init__ with token and {len(initial_channels)} channels")
        super().__init__(
            token=token,
            prefix='!',
            initial_channels=initial_channels
        )
        logger.info("[OK] TwitchIO Bot initialized")
        logger.info(f"[DEBUG] Bot nick: {getattr(self, 'nick', 'NOT SET')}")
        logger.info(f"[DEBUG] Bot user_id: {getattr(self, 'user_id', 'NOT SET')}")

    async def event_ready(self):
        """Р’С‹Р·С‹РІР°РµС‚СЃСЏ РєРѕРіРґР° Р±РѕС‚ РіРѕС‚РѕРІ Рє СЂР°Р±РѕС‚Рµ"""
        logger.info('=' * 80)
        logger.info('[BOT] TWITCH BOT READY!')
        logger.info('=' * 80)
        logger.info(f'[INFO] Bot logged in as: {self.nick}')
        logger.info(f'[ID] Bot user id: {self.user_id}')
        logger.info(f'[CHANNELS] Connected to channels: {self.connected_channels}')
        logger.info('[BOT] BOT IS NOW LISTENING FOR MESSAGES IN ALL CHANNELS!')
        logger.info('[BOT] BOT IS NOW LISTENING FOR MESSAGES IN THESE CHANNELS')
        self.ready_event.set()

        for channel in self.connected_channels:
            logger.info(f'[OK] MONITORING CHAT: {channel.name}')
        
        logger.info('=' * 80)

    async def event_message(self, message):
        """РћР±СЂР°Р±РѕС‚РєР° РІС…РѕРґСЏС‰РёС… СЃРѕРѕР±С‰РµРЅРёР№"""
        # РџСЂРѕРїСѓСЃРєР°РµРј СЃРѕРѕР±С‰РµРЅРёСЏ Р±РѕС‚Р°
        if message.echo:
            logger.debug(f"[SKIP] Bot message: {message.content}")
            return


        # Р›РѕРіРёСЂСѓРµРј СЃРѕРѕР±С‰РµРЅРёРµ
        logger.info(f'[CHAT] [TWITCH CHAT] {message.channel.name}: {message.author.name}: {message.content}')

        # РћС‚РїСЂР°РІР»СЏРµРј СЃРѕРѕР±С‰РµРЅРёРµ РІ chatbox С‡РµСЂРµР· WebSocket
        try:
            from utils.websocket_helper import broadcast_chat_message

            # РџР°СЂСЃРёРј СЂРѕР»Рё Рё Р·РЅР°С‡РєРё РёР· Twitch tags
            role = None
            badges_list = []
            emotes_list = []
            source_message_id = None

            # РџСЂРѕРІРµСЂСЏРµРј СЂРѕР»СЊ (broadcaster > moderator > vip > subscriber)
            if message.author.is_broadcaster:
                role = 'broadcaster'
            elif message.author.is_mod:
                role = 'moderator'
            elif hasattr(message.author, 'is_vip') and message.author.is_vip:
                role = 'vip'
            elif message.author.is_subscriber:
                role = 'subscriber'

            # РџР°СЂСЃРёРј badges РёР· tags (РµСЃР»Рё РґРѕСЃС‚СѓРїРЅС‹)
            if hasattr(message, 'tags') and message.tags:
                source_message_id = str(message.tags.get("id") or "").strip() or None
                if 'badges' in message.tags:
                    # Р¤РѕСЂРјР°С‚: "broadcaster/1,subscriber/12"
                    badges_str = message.tags.get('badges', '')
                    logger.debug("[BADGES RAW] %s: %r", message.author.name, badges_str)
                    if badges_str:
                        badges_list = badges_str.split(',')
                        logger.debug("[BADGES PARSED] %s: %s", message.author.name, badges_list)

                emotes_tag = message.tags.get('emotes')
                if emotes_tag:
                    emotes_list = self._parse_twitch_emotes(emotes_tag, message.content)

            logger.debug(f"[ROLE] {message.author.name}: role={role}, badges={badges_list}")

            # РћС‚РїСЂР°РІР»СЏРµРј РІ chatbox
            avatar_url = getattr(message.author, 'profile_image', None) or getattr(message.author, 'profile_image_url', None)
            await broadcast_chat_message(
                username=message.author.name,
                content=message.content,
                platform='twitch',
                channel=message.channel.name,
                message_id=source_message_id,
                role=role,
                badges=badges_list if badges_list else None,
                emotes=emotes_list if emotes_list else None,
                avatar_url=avatar_url
            )

            # [OK] РќРћР’РћР•: РЈРІРµР»РёС‡РёРІР°РµРј СЃС‡РµС‚С‡РёРє СЃРѕРѕР±С‰РµРЅРёР№ РґР»СЏ СЃС‚СЂРёРєРѕРІ (С‚РѕР»СЊРєРѕ РµСЃР»Рё СЃС‚СЂРёРє РІРєР»СЋС‡РµРЅ)
            try:
                from services.drops.drops_service import DropsService
                from core.database import get_db
                from repositories.user_repository import UserRepository

                # РС‰РµРј user_id РІР»Р°РґРµР»СЊС†Р° РєР°РЅР°Р»Р° РїРѕ РёРјРµРЅРё РєР°РЅР°Р»Р°
                db = next(get_db())
                try:
                    user_repo = UserRepository(db)
                    channel_owner = user_repo.get_by_twitch_username(message.channel.name)

                    if channel_owner:
                        drops_service = DropsService(db)
                        # [OK] РџСЂРѕРІРµСЂСЏРµРј РІРєР»СЋС‡РµРЅ Р»Рё СЃС‚СЂРёРє РґР»СЏ Twitch
                        config = drops_service.get_config(
                            user_id=channel_owner.id,
                            session_id=None,
                            channel_name=message.channel.name.lower(),
                            platform=None  # РћР±С‰РёР№ РєРѕРЅС„РёРі
                        )

                        # РџСЂРѕРІРµСЂСЏРµРј РІРєР»СЋС‡РµРЅ Р»Рё СЃС‚СЂРёРє РґР»СЏ Twitch
                        streak_enabled = False
                        if config:
                            streak_enabled = getattr(config, 'streak_enabled_twitch', False)

                        # РЈРІРµР»РёС‡РёРІР°РµРј СЃС‡РµС‚С‡РёРє С‚РѕР»СЊРєРѕ РµСЃР»Рё СЃС‚СЂРёРє РІРєР»СЋС‡РµРЅ
                        if streak_enabled:
                            drops_service.increment_viewer_message_count(
                                user_id=channel_owner.id,
                                channel_name=message.channel.name.lower(),
                                platform="twitch",
                                viewer_id=str(message.author.id) if hasattr(message.author, 'id') else message.author.name.lower(),
                                viewer_name=message.author.name
                            )
                            try:
                                result = drops_service.process_streak_drops_for_user(
                                    user_id=channel_owner.id,
                                    channel_name=message.channel.name.lower(),
                                    platform="twitch",
                                    viewer_id=str(message.author.id) if hasattr(message.author, 'id') else message.author.name.lower(),
                                    viewer_name=message.author.name,
                                    source_event_id=source_message_id,
                                )
                                if result:
                                    logger.info("[DROPS TWITCH] %s pending streak chest: %s", result.get("viewer_name"), result.get("quality"))
                            except Exception as drops_err:
                                logger.debug(f"Could not process streak drops for Twitch: {drops_err}")
                finally:
                    db.close()
            except Exception as streak_err:
                logger.debug(f"Could not increment streak message count: {streak_err}")

            # NOTE: TTS РѕР±СЂР°Р±Р°С‚С‹РІР°РµС‚СЃСЏ РІ twitch_bot.py::_handle_tts()
            # РќРµ РґСѓР±Р»РёСЂСѓРµРј РІС‹Р·РѕРІ Р·РґРµСЃСЊ!

        except Exception as e:
            logger.error(f'[ERROR] [ERROR] Failed to process chat message: {e}')
            import traceback
            logger.error(traceback.format_exc())

        # РћР±СЂР°Р±Р°С‚С‹РІР°РµРј РєРѕРјР°РЅРґС‹
        await self.handle_commands(message)

    @staticmethod
    def _parse_twitch_emotes(emotes_tag: str, content: str) -> List[dict]:
        """
        Parse Twitch emotes tag into list of {id, name, start, end}.
        Example tag: "25:0-4,12-16/1902:6-10"
        """
        if not emotes_tag or not content:
            return []

        parsed = []
        try:
            for emote_block in emotes_tag.split('/'):
                if ':' not in emote_block:
                    continue
                emote_id, positions = emote_block.split(':', 1)
                for position in positions.split(','):
                    if "-" not in position:
                        continue
                    start_str, end_str = position.split('-', 1)
                    start = int(start_str)
                    end = int(end_str)
                    name = content[start:end + 1]
                    parsed.append({
                        "id": emote_id,
                        "name": name,
                        "start": start,
                        "end": end
                    })
        except Exception as exc:
            logger.debug(f"[WARN] Failed to parse emotes tag '{emotes_tag}': {exc}")
            return []

        return parsed

    async def event_channel_joined(self, channel):
        """Р’С‹Р·С‹РІР°РµС‚СЃСЏ РїСЂРё РїРѕРґРєР»СЋС‡РµРЅРёРё Рє РєР°РЅР°Р»Сѓ"""
        logger.info(f'[JOIN] Joined channel: {channel.name}')

    async def event_channel_left(self, channel):
        """Р’С‹Р·С‹РІР°РµС‚СЃСЏ РїСЂРё РѕС‚РєР»СЋС‡РµРЅРёРё РѕС‚ РєР°РЅР°Р»Р°"""
        logger.info(f'[LEFT] Left channel: {channel.name}')

    async def event_error(self, error):
        """РћР±СЂР°Р±РѕС‚РєР° РѕС€РёР±РѕРє"""
        logger.error(f'[ERROR] Twitch bot error: {error}')

    def get_channel_info(self, channel_name: str) -> Optional[dict]:
        """РџРѕР»СѓС‡РёС‚СЊ РёРЅС„РѕСЂРјР°С†РёСЋ Рѕ РєР°РЅР°Р»Рµ"""
        for channel in self.connected_channels:
            if channel.name.lower() == channel_name.lower():
                return {
                    'name': channel.name,
                    'id': getattr(channel, 'id', None),
                    'connected': True
                }
        return None

    def is_connected_to_channel(self, channel_name: str) -> bool:
        """РџСЂРѕРІРµСЂРёС‚СЊ РїРѕРґРєР»СЋС‡РµРЅРёРµ Рє РєР°РЅР°Р»Сѓ"""
        return any(channel.name.lower() == channel_name.lower()
                  for channel in self.connected_channels)

    async def join_channel(self, channel_name: str):
        """РџРѕРґРєР»СЋС‡РёС‚СЊСЃСЏ Рє РєР°РЅР°Р»Сѓ"""
        try:
            await self.join_channels([channel_name])
            logger.info(f'[JOIN] Joined channel: {channel_name}')
            return True
        except Exception as e:
            logger.error(f'[ERROR] Failed to join channel {channel_name}: {e}')
            return False

    async def leave_channel(self, channel_name: str):
        """РћС‚РєР»СЋС‡РёС‚СЊСЃСЏ РѕС‚ РєР°РЅР°Р»Р°"""
        try:
            await self.part_channels([channel_name])
            logger.info(f'[LEFT] Left channel: {channel_name}')
            return True
        except Exception as e:
            logger.error(f'[ERROR] Failed to leave channel {channel_name}: {e}')
            return False

    def get_connected_channels_list(self) -> List[str]:
        """РџРѕР»СѓС‡РёС‚СЊ СЃРїРёСЃРѕРє РїРѕРґРєР»СЋС‡РµРЅРЅС‹С… РєР°РЅР°Р»РѕРІ"""
        return [channel.name for channel in self.connected_channels]
