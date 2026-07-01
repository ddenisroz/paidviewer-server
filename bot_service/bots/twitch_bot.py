# bot_service/bots/twitch_bot.py
"""Р“Р»Р°РІРЅС‹Р№ С„Р°Р№Р» Twitch Р±РѕС‚Р° - РѕР±СЉРµРґРёРЅСЏРµС‚ РІСЃРµ РјРѕРґСѓР»Рё"""
import logging
from typing import List
from core.connection_manager import ConnectionManager
from utils.role_checker import RoleChecker
from .twitch_bot_core import TwitchBotCore
from .universal_command_handler import UniversalCommandHandler
from services.tts.tts_core import TTSAPI
from services.youtube.youtube_service import YouTubeService
from services.youtube.reward_settings import get_platform_reward_configuration
from services.drops.drops_service import DropsService

logger = logging.getLogger('bot_service')

class Bot(TwitchBotCore):
    """Р“Р»Р°РІРЅС‹Р№ РєР»Р°СЃСЃ Twitch Р±РѕС‚Р°"""
    
    def __init__(self, token: str, initial_channels: List[str], connection_manager: ConnectionManager):
        super().__init__(token, initial_channels, connection_manager)
        
        # РРЅРёС†РёР°Р»РёР·РёСЂСѓРµРј СЃРµСЂРІРёСЃС‹
        self.tts_api = TTSAPI()
        self.youtube_service = YouTubeService()
        self.role_checker = RoleChecker()
        self.drops_service = None  # Р‘СѓРґРµС‚ РёРЅРёС†РёР°Р»РёР·РёСЂРѕРІР°РЅ РїСЂРё РїРѕРґРєР»СЋС‡РµРЅРёРё Рє РєР°РЅР°Р»Сѓ
        
        # РЈРЅРёРІРµСЂСЃР°Р»СЊРЅР°СЏ СЃРёСЃС‚РµРјР° РєРѕРјР°РЅРґ (РґР»СЏ РІСЃРµС… РїР»Р°С‚С„РѕСЂРј)
        self.universal_command_handler = UniversalCommandHandler()
        
        logger.info("[BOT] Universal command handler initialized")
        logger.info("[BOT] Twitch bot initialized with all modules")

    async def event_ready(self):
        """Р’С‹Р·С‹РІР°РµС‚СЃСЏ РєРѕРіРґР° Р±РѕС‚ РіРѕС‚РѕРІ Рє СЂР°Р±РѕС‚Рµ"""
        await super().event_ready()
        logger.info("[BOT] All modules loaded and ready!")
    
    async def send_welcome_message(self, channel_name: str):
        """
        РћС‚РїСЂР°РІРёС‚СЊ РїСЂРёРІРµС‚СЃС‚РІРµРЅРЅРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ РІ РєР°РЅР°Р»
        Р’С‹Р·С‹РІР°РµС‚СЃСЏ С‚РѕР»СЊРєРѕ РїРѕСЃР»Рµ OAuth Р°РІС‚РѕСЂРёР·Р°С†РёРё/РїРµСЂРµРїРѕРґРєР»СЋС‡РµРЅРёСЏ
        """
        try:
            # РќР°С…РѕРґРёРј РѕР±СЉРµРєС‚ РєР°РЅР°Р»Р°
            channel = None
            for ch in self.connected_channels:
                if ch.name.lower() == channel_name.lower():
                    channel = ch
                    break
            
            if not channel:
                logger.warning(f"[WARN] [BOT] Channel {channel_name} not found in connected_channels")
                return
            
            # РџСЂРѕРІРµСЂСЏРµРј РІ Р‘Р”, РЅРµ РѕС‚РїСЂР°РІР»СЏР»Рё Р»Рё РїСЂРёРІРµС‚СЃС‚РІРёРµ РЅРµРґР°РІРЅРѕ
            from core.database import SessionLocal
            from repositories.user_settings_repository import UserSettingsRepository
            from datetime import timedelta
            from core.datetime_utils import utcnow_naive
            
            db = SessionLocal()
            try:
                settings_repo = UserSettingsRepository(db)
                settings = settings_repo.get_by_channel_name(channel_name)
                
                if settings and settings.bot_last_welcome_at:
                    time_diff = utcnow_naive() - settings.bot_last_welcome_at
                    if time_diff < timedelta(minutes=5):
                        logger.debug(f"[MUTE] [BOT] Welcome message sent {int(time_diff.total_seconds())}s ago, skipping")
                        return
                
                # РћС‚РїСЂР°РІР»СЏРµРј РїСЂРёРІРµС‚СЃС‚РІРёРµ
                import random
                fake_ip = f"{random.randint(100, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}"
                await channel.send(f"РџРѕРґРєР»СЋС‡РµРЅРѕ Рє {channel.name}. streamer IP: {fake_ip} | РСЃРїРѕР»СЊР·СѓР№С‚Рµ !help РґР»СЏ СЃРїРёСЃРєР° РєРѕРјР°РЅРґ")
                
                # РћР±РЅРѕРІР»СЏРµРј РІСЂРµРјСЏ РІ Р‘Р”
                if settings:
                    settings.bot_last_welcome_at = utcnow_naive()
                    db.commit()
                
                logger.info(f"[OK] [BOT] Welcome message sent to {channel.name} with fake IP: {fake_ip}")
                
            except Exception as e:
                logger.error(f"[ERROR] [BOT] Failed to send welcome message: {e}")
                await self._handle_ban_error(channel_name, e)
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"[ERROR] [BOT] Error in send_welcome_message: {e}")
    
    async def event_join(self, channel, user):
        """Р’С‹Р·С‹РІР°РµС‚СЃСЏ РєРѕРіРґР° РєС‚Рѕ-С‚Рѕ РїСЂРёСЃРѕРµРґРёРЅСЏРµС‚СЃСЏ Рє РєР°РЅР°Р»Сѓ (РІРєР»СЋС‡Р°СЏ СЃР°РјРѕРіРѕ Р±РѕС‚Р°)"""
        # Р’С‹Р·С‹РІР°РµРј СЂРѕРґРёС‚РµР»СЊСЃРєРёР№ РјРµС‚РѕРґ
        await super().event_join(channel, user)
        
        # Welcome message С‚РµРїРµСЂСЊ РѕС‚РїСЂР°РІР»СЏРµС‚СЃСЏ С‚РѕР»СЊРєРѕ РїСЂРё OAuth РїРѕРґРєР»СЋС‡РµРЅРёРё
        # РЎРј. send_welcome_message() - РІС‹Р·С‹РІР°РµС‚СЃСЏ РёР· oauth_handler РїРѕСЃР»Рµ Р°РІС‚РѕСЂРёР·Р°С†РёРё
        if user.name.lower() == self.nick.lower():
            logger.info(f"[OK] [BOT] Joined channel {channel.name} (welcome message via OAuth only)")
    
    async def _handle_ban_error(self, channel_name: str, error: Exception):
        """РћР±СЂР°Р±РѕС‚РєР° РѕС€РёР±РѕРє, СЃРІСЏР·Р°РЅРЅС‹С… СЃ Р±Р°РЅРѕРј Р±РѕС‚Р°"""
        error_str = str(error).lower()
        
        # РџСЂРѕРІРµСЂСЏРµРј РїСЂРёР·РЅР°РєРё Р±Р°РЅР°
        ban_indicators = ['banned', 'timed out', 'msg_banned', 'msg_timeout', 'forbidden', '403']
        is_banned = any(indicator in error_str for indicator in ban_indicators)
        
        if is_banned:
            logger.warning(f"[BLOCKED] [BOT BAN] Bot appears to be banned/timed out in channel: {channel_name}")
            await self._disconnect_and_cleanup(channel_name, "ban_detected")
    
    async def _disconnect_and_cleanup(self, channel_name: str, reason: str = "ban"):
        """РћС‚РєР»СЋС‡РёС‚СЊСЃСЏ РѕС‚ РєР°РЅР°Р»Р° Рё СѓРґР°Р»РёС‚СЊ С‚РѕРєРµРЅС‹"""
        try:
            logger.warning(f"[CONNECT] [DISCONNECT] Disconnecting from {channel_name} due to: {reason}")
            
            # РџРѕР»СѓС‡Р°РµРј user_id РёР· Р‘Р” РїРѕ РёРјРµРЅРё РєР°РЅР°Р»Р°
            from core.database import SessionLocal
            from repositories.user_repository import UserRepository
            
            db = SessionLocal()
            try:
                user_repo = UserRepository(db)
                user = user_repo.get_by_twitch_username(channel_name)
                
                if user:
                    logger.info(f"[DELETE] [CLEANUP] Found user {user.id} for channel {channel_name}")
                    
                    # РЈРґР°Р»СЏРµРј С‚РѕРєРµРЅС‹
                    from core.session_manager import session_manager
                    session_manager.remove_platform_token(user.id, 'twitch')
                    logger.info(f"[OK] [CLEANUP] Twitch tokens removed for user {user.id}")
                    
                    # РћС‚РєР»СЋС‡Р°РµРј TTS
                    self.connection_manager.disable_tts_for_channel(channel_name.lower())
                    logger.info(f"[OK] [CLEANUP] TTS disabled for {channel_name}")
                    
                    # Р—Р°РІРµСЂС€Р°РµРј СЃРµСЃСЃРёРё СЃ РїСЂРёС‡РёРЅРѕР№ Р±Р°РЅР°
                    session_manager.terminate_user_sessions(user.id, f"bot_{reason}", db)
                    logger.info(f"[OK] [CLEANUP] Sessions terminated for user {user.id}")
                else:
                    logger.warning(f"[WARN] [CLEANUP] User not found for channel {channel_name}")
            finally:
                db.close()
            
            # РџРѕРєРёРґР°РµРј РєР°РЅР°Р»
            try:
                await self.part_channels([channel_name])
                logger.info(f"[OK] [DISCONNECT] Bot left channel: {channel_name}")
            except Exception as e:
                logger.error(f"[ERROR] [DISCONNECT] Error leaving channel {channel_name}: {e}")
                
        except Exception as e:
            logger.error(f"[ERROR] [CLEANUP] Error during disconnect and cleanup for {channel_name}: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def event_raw_data(self, data: str):
        """РћР±СЂР°Р±РѕС‚РєР° raw IRC РґР°РЅРЅС‹С… РґР»СЏ РѕС‚Р»РѕРІР° Р±Р°РЅРѕРІ"""
        try:
            # РџСЂРѕРІРµСЂСЏРµРј С‡С‚Рѕ data - СЃС‚СЂРѕРєР°
            if not isinstance(data, str):
                return
            
            # РћС‚Р»Р°РІР»РёРІР°РµРј CLEARCHAT РґР»СЏ Р±Р°РЅР° Р±РѕС‚Р°
            if 'CLEARCHAT' in data:
                parts = data.split(' ')
                if len(parts) >= 4:
                    channel = parts[3].replace('#', '').strip()
                    # РџСЂРѕРІРµСЂСЏРµРј РµСЃР»Рё Р·Р°Р±Р°РЅРµРЅ РёРјРµРЅРЅРѕ РЅР°С€ Р±РѕС‚
                    if f':{self.nick}' in data.lower():
                        logger.warning(f"[BLOCKED] [BOT BAN] Bot banned/timed out in channel: {channel}")
                        await self._disconnect_and_cleanup(channel, "ban_detected")
        except Exception as e:
            logger.error(f"Error processing raw data for ban detection: {e}")
            import traceback
            logger.debug(traceback.format_exc())
    
    async def event_message(self, message):
        """РћР±СЂР°Р±РѕС‚РєР° РІС…РѕРґСЏС‰РёС… СЃРѕРѕР±С‰РµРЅРёР№"""
        # Р’С‹Р·С‹РІР°РµРј СЂРѕРґРёС‚РµР»СЊСЃРєРёР№ РєР»Р°СЃСЃ РґР»СЏ Р±Р°Р·РѕРІРѕР№ РѕР±СЂР°Р±РѕС‚РєРё
        # (С‚СЂР°РЅСЃР»СЏС†РёСЏ РІ WebSocket, Р»РѕРіРёСЂРѕРІР°РЅРёРµ, etc.)
        await super().event_message(message)
        
        # РџСЂРѕРїСѓСЃРєР°РµРј СЌС…Рѕ-СЃРѕРѕР±С‰РµРЅРёСЏ Р±РѕС‚Р°
        if message.echo:
            return
        
        # РћР±СЂР°Р±РѕС‚РєР° Р·Р°РєР°Р·Р° РІРёРґРµРѕ С‡РµСЂРµР· РЅР°РіСЂР°РґСѓ (Channel Points)
        if hasattr(message, 'tags') and message.tags and message.tags.get('custom-reward-id'):
            try:
                reward_id = message.tags.get('custom-reward-id')
                from core.database import SessionLocal
                from repositories.user_repository import UserRepository
                from repositories.tts_settings_repository import TTSSettingsRepository
                from services.memealerts_service import MemeAlertsService
                
                db = SessionLocal()
                try:
                    user_repo = UserRepository(db)
                    user = user_repo.get_by_twitch_username(message.channel.name)
                    
                    if user:
                        memealerts_service = MemeAlertsService(db)
                        meme_reward_result = await memealerts_service.process_points_reward_redemption(
                            user_id=user.id,
                            platform="twitch",
                            channel_name=message.channel.name,
                            redeemer_name=message.author.name,
                            reward_input=message.content.strip(),
                            reward_id=reward_id,
                        )
                        if meme_reward_result.get("handled"):
                            try:
                                from services.platform_rewards_service import get_platform_rewards_service

                                rewards_service = get_platform_rewards_service()
                                redemptions = await rewards_service.get_redemptions(
                                    user.id,
                                    "twitch",
                                    reward_id,
                                    "UNFULFILLED",
                                    db,
                                )
                                target_status = "FULFILLED" if meme_reward_result.get("success") else "CANCELED"
                                for redemption in redemptions:
                                    if str(redemption.get("user_name", "")).lower() != message.author.name.lower():
                                        continue
                                    if str(redemption.get("user_input", "")).strip() != message.content.strip():
                                        continue
                                    redemption_id = str(redemption.get("id") or "").strip()
                                    if redemption_id:
                                        await rewards_service.update_redemption_status(
                                            user.id,
                                            "twitch",
                                            reward_id,
                                            redemption_id,
                                            target_status,
                                            db,
                                        )
                                    break
                            except Exception:
                                logger.warning("Failed to update MemeAlerts Twitch redemption status", exc_info=True)

                            if meme_reward_result.get("success"):
                                await message.channel.send(
                                    f"@{message.author.name}, РІС‹РґР°РЅРѕ {meme_reward_result.get('amount')} "
                                    f"РјРµРјРєРѕРёРЅРѕРІ РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ {meme_reward_result.get('nickname')}"
                                )
                            else:
                                await message.channel.send(
                                    f"@{message.author.name}, {meme_reward_result.get('error', 'РЅРµ СѓРґР°Р»РѕСЃСЊ РІС‹РґР°С‚СЊ РјРµРјРєРѕРёРЅС‹')}"
                                )
                            return

                        tts_repo = TTSSettingsRepository(db)
                        tts_settings = tts_repo.get_or_create(user_id=user.id)
                        yt_settings = getattr(tts_settings, 'youtube_settings', {}) or {}

                        reward_config = get_platform_reward_configuration(yt_settings, platform='twitch')
                        twitch_reward_enabled = bool(reward_config.get('enabled'))
                        twitch_reward_id = str(reward_config.get('reward_value') or '').strip()

                        if twitch_reward_enabled and twitch_reward_id and twitch_reward_id == reward_id:
                            logger.info(f"[YOUTUBE] Detected Request via Reward: {reward_id}")
                            
                            from services.youtube.queue_service import QueueService
                            queue_service = QueueService()
                            
                            # Use message content as URL
                            url = message.content.strip()
                            if url:
                                result = await queue_service.add_video(
                                    user_id=user.id,
                                    url=url,
                                    requested_by=message.author.name,
                                    requester_id=str(message.author.id),
                                    platform='twitch',
                                    is_paid=True
                                )
                                
                                if result.get('success'):
                                    await message.channel.send(f"@{message.author.name}, РІРёРґРµРѕ РґРѕР±Р°РІР»РµРЅРѕ Р·Р° Р±Р°Р»Р»С‹: {result.get('title', 'Video')[:40]}")
                                else:
                                    await message.channel.send(f"@{message.author.name}, РѕС€РёР±РєР° РґРѕР±Р°РІР»РµРЅРёСЏ: {result.get('error')}")
                                
                                return # Stop further processing (TTS) for this message
                finally:
                    db.close()
            except Exception as e:
                logger.error(f"[ERROR] Error processing reward request: {e}")

        # РџСЂРѕРІРµСЂРєР° РєРѕРјР°РЅРґС‹ (СѓРЅРёРІРµСЂСЃР°Р»СЊРЅР°СЏ СЃРёСЃС‚РµРјР°)
        if message.content.strip().startswith('!'):
            # РЎРѕР·РґР°РµРј ctx-СЃРѕРІРјРµСЃС‚РёРјС‹Р№ РѕР±СЉРµРєС‚ РґР»СЏ universal_command_handler
            class SimpleContext:
                def __init__(self, msg, bot):
                    self.message = msg
                    self.author = msg.author
                    self.channel = msg.channel
                    self.bot = bot
                
                async def send(self, content):
                    await self.channel.send(content)
            
            ctx = SimpleContext(message, self)
            await self.universal_command_handler.handle_twitch_command(ctx, self)
            return

        await self.universal_command_handler.handle_twitch_message(message, self)  # РќРµ РѕР±СЂР°Р±Р°С‚С‹РІР°РµРј TTS РґР»СЏ РєРѕРјР°РЅРґ
        
        # РћР±СЂР°Р±РѕС‚РєР° TTS РґР»СЏ РІСЃРµС… СЃРѕРѕР±С‰РµРЅРёР№ (СЂРѕРґРёС‚РµР»СЊ СѓР¶Рµ С‚СЂР°РЅСЃР»СЏРµС‚ СЃРѕРѕР±С‰РµРЅРёРµ)
        await self._handle_tts(message)
        
        # РћР±СЂР°Р±РѕС‚РєР° Drops РґР»СЏ СЃС‚СЂРёРєРѕРІ
        await self._handle_drops(message)
    
    async def handle_commands(self, message):
        """РџРµСЂРµРѕРїСЂРµРґРµР»СЏРµРј handle_commands С‡С‚РѕР±С‹ РѕС‚РєР»СЋС‡РёС‚СЊ Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєСѓСЋ РѕР±СЂР°Р±РѕС‚РєСѓ TwitchIO"""
        # РљРѕРјР°РЅРґС‹ РѕР±СЂР°Р±Р°С‚С‹РІР°СЋС‚СЃСЏ РІ event_message С‡РµСЂРµР· UniversalCommandHandler
        # РќРµ РІС‹Р·С‹РІР°РµРј super().handle_commands()
        pass

    async def _handle_tts(self, message):
        """РћР±СЂР°Р±РѕС‚РєР° TTS РґР»СЏ СЃРѕРѕР±С‰РµРЅРёР№ РёР· Twitch"""
        from utils.websocket_helper import handle_tts_for_message
        from utils.tts_message_context import extract_twitch_tts_context
        
        # РР·РІР»РµРєР°РµРј reward_id РёР· IRC tags РµСЃР»Рё СЃРѕРѕР±С‰РµРЅРёРµ РѕС‚РїСЂР°РІР»РµРЅРѕ СЃ РЅР°РіСЂР°РґРѕР№
        reward_id = None
        source_message_id = None
        message_context = extract_twitch_tts_context(message)
        if hasattr(message, 'tags') and message.tags:
            reward_id = message.tags.get('custom-reward-id')
            source_message_id = str(message.tags.get("id") or "").strip() or None
            if reward_id:
                logger.info(f"[REWARD] [TWITCH MSG] Message from Channel Points reward: {reward_id}")
        
        await handle_tts_for_message(
            text=message.content,
            username=message.author.name.lower(),
            channel_identifier=message.channel.name.lower(),
            platform='twitch',
            tts_api=self.tts_api,
            connection_manager=self.connection_manager,
            skip_if_command=True,
            is_reply=bool(message_context.get("is_reply")),
            mentioned_users=message_context.get("mentioned_users") or [],
            reward_id=reward_id,
            message_id=source_message_id,
        )

    async def _handle_drops(self, message):
        """РћР±СЂР°Р±РѕС‚РєР° Drops РґР»СЏ СЃРѕРѕР±С‰РµРЅРёР№ РёР· Twitch"""
        try:
            # РРЅРёС†РёР°Р»РёР·РёСЂСѓРµРј DropsService РµСЃР»Рё РµС‰Рµ РЅРµ РёРЅРёС†РёР°Р»РёР·РёСЂРѕРІР°РЅ
            if not self.drops_service:
                from core.database import get_db
                db = next(get_db())
                self.drops_service = DropsService(db)
            
            # РџРѕР»СѓС‡Р°РµРј РёРЅС„РѕСЂРјР°С†РёСЋ Рѕ РїРѕР»СЊР·РѕРІР°С‚РµР»Рµ
            user_id = self._get_user_id_for_channel(message.channel.name)
            if not user_id:
                return
            
            # РћР±СЂР°Р±Р°С‚С‹РІР°РµРј СЃС‚СЂРёРє Drops
            result = self.drops_service.process_streak_drops_for_user(
                user_id=user_id,
                channel_name=message.channel.name,
                platform='twitch',
                viewer_id=message.author.id,
                viewer_name=message.author.name
            )
            
            if result:
                logger.info("[DROPS] %s pending streak chest: %s", result.get("viewer_name"), result.get("quality"))
                
        except Exception as e:
            logger.error(f"Error handling drops: {e}")
    
    def _get_user_id_for_channel(self, channel_name: str) -> int:
        """РџРѕР»СѓС‡Р°РµС‚ user_id РґР»СЏ РєР°РЅР°Р»Р°"""
        try:
            from core.database import get_db
            from repositories.user_repository import UserRepository
            
            db = next(get_db())
            
            # РС‰РµРј РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ РїРѕ Twitch username (case-insensitive)
            user_repo = UserRepository(db)
            user = user_repo.get_by_twitch_username(channel_name)
            
            if user:
                return user.id
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting user_id for channel {channel_name}: {e}")
            return None

    async def event_channel_joined(self, channel):
        """Р’С‹Р·С‹РІР°РµС‚СЃСЏ РїСЂРё РїРѕРґРєР»СЋС‡РµРЅРёРё Рє РєР°РЅР°Р»Сѓ"""
        await super().event_channel_joined(channel)
        
        # РЈРІРµРґРѕРјР»СЏРµРј connection_manager
        self.connection_manager.add_active_session(
            channel.name, 
            f"twitch_{channel.name}",
            "twitch"
        )

    async def event_channel_left(self, channel):
        """Р’С‹Р·С‹РІР°РµС‚СЃСЏ РїСЂРё РѕС‚РєР»СЋС‡РµРЅРёРё РѕС‚ РєР°РЅР°Р»Р°"""
        await super().event_channel_left(channel)
        
        # РЈРІРµРґРѕРјР»СЏРµРј connection_manager
        self.connection_manager.remove_active_session(
            channel.name, 
            "twitch_disconnect"
        )

    async def event_error(self, error):
        """РћР±СЂР°Р±РѕС‚РєР° РѕС€РёР±РѕРє"""
        await super().event_error(error)
        logger.error(f"[ERROR] Twitch bot error: {error}")

    def get_stats(self) -> dict:
        """РџРѕР»СѓС‡РёС‚СЊ СЃС‚Р°С‚РёСЃС‚РёРєСѓ Р±РѕС‚Р°"""
        return {
            "connected_channels": len(self.connected_channels),
            "channels": [ch.name for ch in self.connected_channels],
            "is_ready": hasattr(self, 'user_id') and self.user_id is not None,
            "nick": getattr(self, 'nick', 'Unknown')
        }

    async def shutdown(self):
        """РљРѕСЂСЂРµРєС‚РЅРѕРµ Р·Р°РІРµСЂС€РµРЅРёРµ СЂР°Р±РѕС‚С‹ Р±РѕС‚Р°"""
        try:
            logger.info("[BOT] Shutting down Twitch bot...")
            
            # РћС‚РєР»СЋС‡Р°РµРјСЃСЏ РѕС‚ РІСЃРµС… РєР°РЅР°Р»РѕРІ
            if self.connected_channels:
                await self.part_channels([ch.name for ch in self.connected_channels])
            
            logger.info("[BOT] Twitch bot shutdown complete")
        except Exception as e:
            logger.error(f"[ERROR] Error during bot shutdown: {e}")
