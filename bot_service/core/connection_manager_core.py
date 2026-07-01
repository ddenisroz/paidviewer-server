"""Core ConnectionManager logic."""
import logging
import asyncio
from typing import Dict, Set, List, TYPE_CHECKING, Any
from fastapi import WebSocket
from constants import TTS_RECONNECT_TIMEOUT_SECONDS
from core.log_sanitizer import mask_session_id
if TYPE_CHECKING:
    pass
logger = logging.getLogger(__name__)

class ConnectionManagerCore:
    """Core connection management logic."""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.obs_connections: Dict[str, WebSocket] = {}
        self.youtube_obs_connections: Dict[str, WebSocket] = {}
        self.audio_connections: Dict[str, WebSocket] = {}
        self.tts_enabled_channels: Set[str] = set()
        self.tts_enabled_twitch: Set[str] = set()
        self.tts_enabled_vk: Set[str] = set()
        self.basic_tts_enabled_channels: Set[str] = set()
        self.ai_tts_enabled_channels: Set[str] = set()
        self.blocked_bots: Set[str] = set()
        self.youtube_queues: Dict[str, list] = {}
        self.current_videos: Dict[str, dict] = {}
        self.pending_verifications: Dict[str, dict] = {}
        self.verified_sessions: Set[str] = set()
        self.active_vk_bots: Dict[str, dict] = {}
        self.active_sessions: Dict[str, set] = {}
        self.tts_volume_settings: Dict[str, float] = {}
        self.voice_volume_settings: Dict[str, Dict[str, float]] = {}
        self.youtube_settings: Dict[str, dict] = {}
        self.twitch_cache: Dict[str, Any] = {}
        self.pending_tts_disconnects: Dict[int, asyncio.Task] = {}
        self.reconnect_timeout: int = TTS_RECONNECT_TIMEOUT_SECONDS

    def add_active_session(self, channel_name: str, session_id: str, platform: str='twitch'):
        """Add an active session and cancel any scheduled TTS disconnect."""
        if channel_name not in self.active_sessions:
            self.active_sessions[channel_name] = set()
        self.active_sessions[channel_name].add(session_id)
        logger.debug(
            "Added session %s to channel %s (%s)",
            mask_session_id(session_id),
            channel_name,
            platform,
        )
        try:
            from core.database import get_db, User
            db = next(get_db())
            try:
                user = db.query(User).filter((User.twitch_username == channel_name.lower()) | (User.vk_username == channel_name.lower()) | (User.vk_channel_name == channel_name.lower())).first()
                if user:
                    has_site_listener = False
                    has_obs_listener = False
                    try:
                        from services.memory_websocket_manager import get_memory_websocket_manager
                        user_connections = get_memory_websocket_manager().get_user_connections(user.id)
                        has_site_listener = any((conn.get('is_active', True) for conn in user_connections))
                    except Exception as ws_err:
                        logger.debug(f'[DEBUG] [TTS RECONNECT] Failed to check site listeners for user {user.id}: {ws_err}')
                    obs_token = getattr(user, 'obs_token', None)
                    if obs_token and obs_token in self.obs_connections:
                        has_obs_listener = True
                    if has_site_listener or has_obs_listener:
                        logger.info(f'[OK] [TTS RECONNECT] Bot reconnected to {channel_name}, active listener detected, cancelling TTS disconnect for user {user.id}')
                        self.cancel_tts_disconnect(user.id)
                    else:
                        logger.info(f'[SKIP] [TTS RECONNECT] Bot reconnected to {channel_name}, no active listeners for user {user.id}; keeping pending TTS disconnect')
            finally:
                db.close()
        except Exception as e:
            logger.error(f'[ERROR] [TTS RECONNECT] Error cancelling TTS disconnect for {channel_name}: {e}')

    def remove_active_session(self, channel_name: str, reason: str='disconnect') -> bool:
        """Remove an active session and start TTS disconnect timer if needed."""
        if channel_name in self.active_sessions:
            sessions = self.active_sessions[channel_name]
            if sessions:
                session_id = sessions.pop()
                logger.debug(
                    "Removed session %s from channel %s (%s)",
                    mask_session_id(session_id),
                    channel_name,
                    reason,
                )
                if not sessions:
                    del self.active_sessions[channel_name]
                    logger.info(f'[TIMER] [SESSION] Last session removed for {channel_name}, checking TTS disconnect')
                    self._schedule_tts_disconnect_for_channel(channel_name)
                return True
            else:
                del self.active_sessions[channel_name]
                logger.debug(f'Removed empty channel {channel_name} ({reason})')
                self._schedule_tts_disconnect_for_channel(channel_name)
                return True
        return False

    def _schedule_tts_disconnect_for_channel(self, channel_name: str):
        """Schedule TTS disconnect for a channel by resolving its owner."""
        try:
            from core.database import get_db, User
            db = next(get_db())
            try:
                user = db.query(User).filter((User.twitch_username == channel_name.lower()) | (User.vk_username == channel_name.lower()) | (User.vk_channel_name == channel_name.lower())).first()
                if user:
                    logger.info(f'[TIMER] [TTS DISCONNECT] Found user {user.id} for channel {channel_name}')
                    self.schedule_tts_disconnect(user.id, channel_name)
                else:
                    logger.warning(f'[WARN] [TTS DISCONNECT] User not found for channel {channel_name}')
            finally:
                db.close()
        except Exception as e:
            logger.error(f'[ERROR] [TTS DISCONNECT] Error scheduling TTS disconnect for {channel_name}: {e}')

    def get_active_channels(self) -> List[str]:
        """Return active channels."""
        return list(self.active_sessions.keys())

    def get_active_sessions(self) -> Dict[str, set]:
        """Return active sessions."""
        return self.active_sessions.copy()

    def is_channel_active(self, channel_name: str) -> bool:
        """Check whether the channel is active."""
        return channel_name in self.active_sessions and len(self.active_sessions[channel_name]) > 0

    def get_channel_session_count(self, channel_name: str) -> int:
        """Return the channel session count."""
        return len(self.active_sessions.get(channel_name, set()))

    def enable_tts_for_channel(self, channel_name: str, tts_type: str='basic'):
        """Enable TTS for a channel and replace the previous type atomically."""
        normalized_channel = str(channel_name or "").strip().lower()
        if not normalized_channel:
            return

        self.basic_tts_enabled_channels.discard(normalized_channel)
        self.ai_tts_enabled_channels.discard(normalized_channel)

        normalized_type = str(tts_type or "basic").strip().lower()
        if normalized_type == 'ai':
            self.ai_tts_enabled_channels.add(normalized_channel)
        else:
            self.basic_tts_enabled_channels.add(normalized_channel)

        self.tts_enabled_channels.add(normalized_channel)
        logger.info(f'TTS enabled for channel {normalized_channel} (type: {normalized_type})')

    def disable_tts_for_channel(self, channel_name: str):
        """Disable TTS for a channel."""
        normalized_channel = str(channel_name or "").strip().lower()
        if not normalized_channel:
            return

        self.basic_tts_enabled_channels.discard(normalized_channel)
        self.ai_tts_enabled_channels.discard(normalized_channel)
        self.tts_enabled_channels.discard(normalized_channel)
        logger.info(f'TTS disabled for channel {normalized_channel}')

    def is_tts_enabled(self, channel_name: str) -> bool:
        """Check whether TTS is enabled for a channel."""
        is_enabled = channel_name in self.tts_enabled_channels
        logger.debug(f"[TTS CHECK] is_tts_enabled('{channel_name}') = {is_enabled}")
        return is_enabled

    def get_tts_type(self, channel_name: str) -> str:
        """Return the TTS type for a channel."""
        if channel_name in self.ai_tts_enabled_channels:
            return 'ai'
        elif channel_name in self.basic_tts_enabled_channels:
            return 'basic'
        return 'none'

    def set_tts_volume(self, channel_name: str, volume: float):
        """Set TTS volume for a channel."""
        self.tts_volume_settings[channel_name] = max(0.0, min(1.0, volume))
        logger.debug(f'TTS volume set to {volume} for channel {channel_name}')

    def get_tts_volume(self, channel_name: str) -> float:
        """Return TTS volume for a channel."""
        return self.tts_volume_settings.get(channel_name, 1.0)

    def set_voice_volume(self, channel_name: str, voice_name: str, volume: float):
        """Set voice volume for a channel."""
        if channel_name not in self.voice_volume_settings:
            self.voice_volume_settings[channel_name] = {}
        self.voice_volume_settings[channel_name][voice_name] = max(0.0, min(1.0, volume))
        logger.debug(f'Voice {voice_name} volume set to {volume} for channel {channel_name}')

    def get_voice_volume(self, channel_name: str, voice_name: str) -> float:
        """Return voice volume for a channel."""
        return self.voice_volume_settings.get(channel_name, {}).get(voice_name, 1.0)

    def get_stats(self) -> Dict[str, any]:
        """Return connection statistics."""
        return {'active_connections': len(self.active_connections), 'obs_connections': len(self.obs_connections), 'youtube_obs_connections': len(self.youtube_obs_connections), 'audio_connections': len(self.audio_connections), 'active_channels': len(self.active_sessions), 'tts_enabled_channels': len(self.tts_enabled_channels), 'basic_tts_channels': len(self.basic_tts_enabled_channels), 'ai_tts_channels': len(self.ai_tts_enabled_channels), 'active_vk_bots': len(self.active_vk_bots), 'total_sessions': sum((len(sessions) for sessions in self.active_sessions.values()))}

    def get_twitch_cache(self, cache_key: str) -> Any:
        """Return a value from Twitch cache."""
        return self.twitch_cache.get(cache_key)

    def update_twitch_cache(self, cache_key: str, value: Any):
        """Update a value in Twitch cache."""
        self.twitch_cache[cache_key] = value
        logger.debug(f'Updated Twitch cache key: {cache_key}')

    async def _delayed_tts_disable(self, user_id: int, username: str):
        """Disable TTS after a delay."""
        try:
            await asyncio.sleep(self.reconnect_timeout)
            has_active_connections = self._has_active_connections_for_user(user_id)
            if has_active_connections:
                logger.info(f'[OK] [TTS TIMEOUT] User {user_id} ({username}) has active connections - keeping TTS enabled')
                return
            logger.info(f'[TIMEOUT] [TTS TIMEOUT] User {user_id} ({username}) timeout expired, disabling TTS')
            self.disable_tts_for_channel(username)
            try:
                from core.database import SessionLocal
                from services.tts.tts_service import TTSService
                db = SessionLocal()
                try:
                    tts_service = TTSService(db)
                    await tts_service.disable_tts(user_id=user_id)
                    logger.info(f'[OK] [TTS TIMEOUT] TTS disabled for user {user_id} ({username})')
                finally:
                    db.close()
            except Exception as disable_err:
                logger.error(f'[ERROR] [TTS TIMEOUT] Failed to disable TTS in DB for user {user_id}: {disable_err}')
        except asyncio.CancelledError:
            logger.info(f'[OK] [TTS RECONNECT] User {user_id} reconnected - keeping TTS enabled')
            raise
        except Exception as e:
            logger.error(f'[ERROR] [TTS TIMEOUT] Error handling timeout for user {user_id}: {e}')
        finally:
            if user_id in self.pending_tts_disconnects:
                del self.pending_tts_disconnects[user_id]
                logger.debug(f'[DELETE] [TTS CLEANUP] Removed pending disconnect task for user {user_id}')

    def _has_active_connections_for_user(self, user_id: int) -> bool:
        """
        Check whether the user still has active listener and bot connections.
        """
        try:
            has_listeners = False
            has_active_bots = False
            from services.memory_websocket_manager import get_memory_websocket_manager
            user_connections = get_memory_websocket_manager().get_user_connections(user_id)
            if user_connections:
                active_connections = [conn for conn in user_connections if conn.get('is_active', True)]
                if active_connections:
                    logger.info(f'[DEBUG] [TTS CHECK] User {user_id} has {len(active_connections)} active WebSocket connections (site)')
                    has_listeners = True
            from core.database import get_db, User
            db = next(get_db())
            try:
                user = db.query(User).filter(User.id == user_id).first()
                if user:
                    if user.obs_token and user.obs_token in self.obs_connections:
                        logger.info(f'[DEBUG] [TTS CHECK] User {user_id} has OBS connection in registry')
                        has_listeners = True
                    if user.twitch_username:
                        if self.is_channel_active(user.twitch_username):
                            logger.info(f'[DEBUG] [TTS CHECK] User {user_id} has active Twitch bot sessions for {user.twitch_username}')
                            has_active_bots = True
                    if user.vk_username or user.vk_channel_name:
                        vk_channel = user.vk_channel_name or user.vk_username
                        if vk_channel and self.is_channel_active(vk_channel):
                            logger.info(f'[DEBUG] [TTS CHECK] User {user_id} has active VK bot sessions for {vk_channel}')
                            has_active_bots = True
            finally:
                db.close()
            result = has_listeners and has_active_bots
            if not has_listeners:
                logger.info(f'[DEBUG] [TTS CHECK] User {user_id} has NO listeners (no WebSocket site, no OBS) - TTS will be disabled')
            elif not has_active_bots:
                logger.info(f'[DEBUG] [TTS CHECK] User {user_id} has NO active bot connections on platforms - TTS will be disabled')
            else:
                logger.info(f'[DEBUG] [TTS CHECK] User {user_id} has both listeners AND active bots - keeping TTS enabled')
            return result
        except Exception as e:
            logger.error(f'[ERROR] [TTS CHECK] Error checking active connections for user {user_id}: {e}')
            return False

    def schedule_tts_disconnect(self, user_id: int, username: str):
        """Schedule a delayed TTS disconnect task."""
        self.cancel_tts_disconnect(user_id)
        task = asyncio.create_task(self._delayed_tts_disable(user_id, username))
        self.pending_tts_disconnects[user_id] = task

        def cleanup_callback(finished_task):
            if self.pending_tts_disconnects.get(user_id) == finished_task:
                try:
                    finished_task.exception()
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error(f'[ERROR] [TTS TASK] Unexpected error in disconnect task for user {user_id}: {e}')
        task.add_done_callback(cleanup_callback)
        logger.info(f'[TIMER] [TTS DISCONNECT] Scheduled TTS disable for user {user_id} ({username}) in {self.reconnect_timeout}s')

    def cancel_tts_disconnect(self, user_id: int):
        """Cancel a previously scheduled TTS disconnect task."""
        if user_id in self.pending_tts_disconnects:
            task = self.pending_tts_disconnects[user_id]
            if not task.done():
                task.cancel()
                logger.info(f'[REFRESH] [TTS RECONNECT] Cancelled scheduled TTS disable for user {user_id}')
            del self.pending_tts_disconnects[user_id]
