# bot_service/core/connection_manager.py
"""Main ConnectionManager module that combines all submodules."""
import asyncio
import inspect
import logging
from typing import Any, List, TYPE_CHECKING
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState
from .connection_manager_core import ConnectionManagerCore
from core.log_sanitizer import mask_session_id

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Global ConnectionManager singleton.
_connection_manager_instance = None

def get_connection_manager():
    """Return the global ConnectionManager singleton."""
    global _connection_manager_instance
    if _connection_manager_instance is None:
        _connection_manager_instance = ConnectionManager()
        logger.info("[FIX] Created global ConnectionManager instance")
    return _connection_manager_instance

class ConnectionManager(ConnectionManagerCore):
    """Main connection manager class."""

    def __init__(self):
        super().__init__()
        self.youtube_obs_user_ids: dict[str, int] = {}
        logger.info("[CONNECTION] ConnectionManager initialized")

    @staticmethod
    def _channel_keys(channel_name: str) -> tuple[str, ...]:
        raw_channel = str(channel_name or "").strip()
        normalized_channel = raw_channel.lower()
        return tuple(dict.fromkeys(key for key in (raw_channel, normalized_channel) if key))

    @staticmethod
    def _is_websocket_connected(websocket: Any) -> bool:
        client_state = getattr(websocket, "client_state", None)
        application_state = getattr(websocket, "application_state", None)
        return (
            client_state == WebSocketState.CONNECTED
            and application_state != WebSocketState.DISCONNECTED
        )

    @staticmethod
    def _run_awaitable_best_effort(awaitable) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(awaitable)
        else:
            loop.create_task(awaitable)

    @staticmethod
    def _verify_obs_audio_token(token: str) -> dict | None:
        from auth.auth import verify_jwt_token

        for expected_type in ("tts_source", "obs"):
            try:
                return verify_jwt_token(token, expected_type=expected_type)
            except Exception:
                continue
        return None

    @classmethod
    def _close_websocket_best_effort(cls, websocket: Any) -> None:
        close_method = getattr(websocket, "close", None)
        if not callable(close_method):
            return

        try:
            result = close_method()
            if inspect.isawaitable(result):
                cls._run_awaitable_best_effort(result)
        except Exception:
            logger.debug("Failed to close websocket during cleanup", exc_info=True)

    def _cancel_pending_disconnects(self) -> None:
        for user_id, task in list(self.pending_tts_disconnects.items()):
            if task and not task.done():
                task.cancel()
                logger.debug("Cancelled pending TTS disconnect task for user %s during cleanup", user_id)
        self.pending_tts_disconnects.clear()

    def _clear_runtime_state(self) -> None:
        for mapping in (
            self.active_connections,
            self.obs_connections,
            self.youtube_obs_connections,
            self.audio_connections,
            self.youtube_queues,
            self.current_videos,
            self.pending_verifications,
            self.active_vk_bots,
            self.active_sessions,
            self.tts_volume_settings,
            self.voice_volume_settings,
            self.youtube_settings,
            self.twitch_cache,
            self.youtube_obs_user_ids,
        ):
            mapping.clear()

        for collection in (
            self.tts_enabled_channels,
            self.tts_enabled_twitch,
            self.tts_enabled_vk,
            self.basic_tts_enabled_channels,
            self.ai_tts_enabled_channels,
            self.blocked_bots,
            self.verified_sessions,
        ):
            collection.clear()

    async def connect(self, websocket: WebSocket, user_id: str):
        """Connect a user WebSocket."""
        try:
            await websocket.accept()
            self.active_connections[user_id] = websocket
            logger.info(f"WebSocket connected: {user_id}")
        except Exception as e:
            logger.error(f"Error connecting WebSocket: {e}")

    async def disconnect(self, user_id: str):
        """Disconnect a user WebSocket."""
        try:
            if user_id in self.active_connections:
                websocket = self.active_connections[user_id]
                await websocket.close()
                del self.active_connections[user_id]
                logger.info(f"WebSocket disconnected: {user_id}")
        except Exception as e:
            logger.error(f"Error disconnecting WebSocket: {e}")

    async def connect_obs(self, websocket: WebSocket, token: str):
        """Connect an OBS WebSocket."""
        try:
            await websocket.accept()
            self.obs_connections[token] = websocket
            logger.info(f"OBS WebSocket connected: {token[:10]}...")

            try:
                payload = self._verify_obs_audio_token(token)
                if payload and 'user_id' in payload:
                    user_id = payload['user_id']
                    self.cancel_tts_disconnect(user_id)
                    try:
                        from services.memory_websocket_manager import get_memory_websocket_manager
                        await get_memory_websocket_manager().sync_user_tts_generation(user_id)
                    except Exception as sync_error:
                        logger.warning(f"Failed to sync TTS generation after OBS connect: {sync_error}")
                    logger.info(f"[OK] [OBS CONNECT] Cancelled TTS disconnect for user {user_id} (OBS connected)")
            except Exception as e:
                logger.debug(f"Could not extract user_id from OBS token: {e}")

        except Exception as e:
            logger.error(f"Error connecting OBS WebSocket: {e}")

    async def disconnect_obs(self, token: str):
        """Disconnect an OBS WebSocket."""
        websocket = self.obs_connections.pop(token, None)
        if not websocket:
            return

        try:
            try:
                await websocket.close()
            except RuntimeError as exc:
                if "websocket.close" not in str(exc):
                    raise
            except Exception as exc:
                logger.debug("OBS WebSocket close skipped for %s...: %s", token[:10], exc)

            logger.info(f"OBS WebSocket disconnected: {token[:10]}...")

            # Schedule TTS disconnect if no other active listeners remain.
            from core.database import get_db, User

            try:
                payload = self._verify_obs_audio_token(token)
                if payload and 'user_id' in payload:
                    user_id = payload['user_id']
                    db = next(get_db())
                    try:
                        user = db.query(User).filter(User.id == user_id).first()
                        if user:
                            username = user.twitch_username or user.vk_username or f"user_{user_id}"
                            # Actual listener checks are handled inside _delayed_tts_disable.
                            self.schedule_tts_disconnect(user_id, username)
                            try:
                                from services.memory_websocket_manager import get_memory_websocket_manager
                                await get_memory_websocket_manager().sync_user_tts_generation(user_id)
                            except Exception as sync_error:
                                logger.warning(f"Failed to sync TTS generation after OBS disconnect: {sync_error}")
                            logger.info(f"[OBS DISCONNECT] Scheduled TTS disconnect for user {user_id} (OBS disconnected)")
                    finally:
                        db.close()
            except Exception as e:
                logger.debug(f"Could not extract user_id from OBS token: {e}")

        except Exception as e:
            logger.error(f"Error disconnecting OBS WebSocket: {e}")

    async def connect_youtube_obs(self, websocket: WebSocket, token: str, user_id: int):
        """Connect a YouTube OBS overlay WebSocket."""
        try:
            await websocket.accept()
            self.youtube_obs_connections[token] = websocket
            self.youtube_obs_user_ids[token] = int(user_id)
            logger.info("YouTube OBS WebSocket connected: user=%s token=%s...", user_id, token[:10])
        except Exception as e:
            logger.error(f"Error connecting YouTube OBS WebSocket: {e}")

    async def disconnect_youtube_obs(self, token: str):
        """Disconnect a YouTube OBS overlay WebSocket."""
        try:
            websocket = self.youtube_obs_connections.pop(token, None)
            self.youtube_obs_user_ids.pop(token, None)
            if websocket and self._is_websocket_connected(websocket):
                await websocket.close()
            logger.info("YouTube OBS WebSocket disconnected: %s...", token[:10])
        except Exception as e:
            logger.error(f"Error disconnecting YouTube OBS WebSocket: {e}")

    async def send_youtube_obs_to_user(self, user_id: int, message: dict):
        """Send a message to all YouTube OBS overlay clients for a user."""
        sent = 0
        disconnected: list[str] = []
        for token, websocket in list(self.youtube_obs_connections.items()):
            if self.youtube_obs_user_ids.get(token) != int(user_id):
                continue
            try:
                await websocket.send_json(message)
                sent += 1
            except WebSocketDisconnect:
                disconnected.append(token)
            except Exception as e:
                logger.warning("Failed to send YouTube OBS update to %s...: %s", token[:10], e)
                disconnected.append(token)

        for token in disconnected:
            self.youtube_obs_connections.pop(token, None)
            self.youtube_obs_user_ids.pop(token, None)
        return sent

    async def send_youtube_to_obs(self, channel_name: str = "", action: str = "queue_update", data: dict | None = None):
        """Backward-compatible YouTube OBS sender used by older queue code."""
        message = {
            "type": "youtube_obs_event",
            "action": action,
            "channel_name": channel_name,
            "data": data or {},
        }
        sent = 0
        disconnected: list[str] = []
        for token, websocket in list(self.youtube_obs_connections.items()):
            try:
                await websocket.send_json(message)
                sent += 1
            except WebSocketDisconnect:
                disconnected.append(token)
            except Exception as e:
                logger.warning("Failed to send legacy YouTube OBS update to %s...: %s", token[:10], e)
                disconnected.append(token)

        for token in disconnected:
            self.youtube_obs_connections.pop(token, None)
            self.youtube_obs_user_ids.pop(token, None)
        return sent

    async def connect_audio(self, websocket: WebSocket, channel: str):
        """Connect an audio WebSocket."""
        try:
            await websocket.accept()
            self.audio_connections[channel] = websocket
            logger.info(f"Audio WebSocket connected: {channel}")
        except Exception as e:
            logger.error(f"Error connecting audio WebSocket: {e}")

    async def disconnect_audio(self, channel: str):
        """Disconnect an audio WebSocket."""
        try:
            if channel in self.audio_connections:
                websocket = self.audio_connections[channel]
                await websocket.close()
                del self.audio_connections[channel]
                logger.info(f"Audio WebSocket disconnected: {channel}")
        except Exception as e:
            logger.error(f"Error disconnecting audio WebSocket: {e}")

    async def send_to_user(self, user_id: str, message: dict):
        """Send a message to a user."""
        try:
            if user_id in self.active_connections:
                websocket = self.active_connections[user_id]
                await websocket.send_json(message)
                logger.debug(f"Message sent to user {user_id}")
                return True
            else:
                logger.warning(f"User {user_id} not connected")
                return False
        except Exception as e:
            logger.error(f"Error sending message to user {user_id}: {e}")
            return False

    async def send_to_channel(self, channel: str, message: dict):
        """Send a message to a channel."""
        try:
            if channel in self.audio_connections:
                websocket = self.audio_connections[channel]
                await websocket.send_json(message)
                logger.debug(f"Message sent to channel {channel}")
                return True
            else:
                logger.warning(f"Channel {channel} not connected")
                return False
        except Exception as e:
            logger.error(f"Error sending message to channel {channel}: {e}")
            return False

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected users."""
        disconnected = []
        for user_id, websocket in self.active_connections.items():
            try:
                await websocket.send_json(message)
            except WebSocketDisconnect:
                disconnected.append(user_id)
            except Exception as e:
                logger.error(f"Error broadcasting to user {user_id}: {e}")
                disconnected.append(user_id)

        # Remove disconnected users.
        for user_id in disconnected:
            del self.active_connections[user_id]
            logger.debug(f"Removed disconnected user: {user_id}")

    async def broadcast_settings_update(self, user_id: str, setting_type: str, settings: dict):
        """Broadcast settings update to user's connections"""
        message = {
            "type": f"{setting_type}_updated",
            "data": {
                "settings": settings
            }
        }
        await self.send_to_user(user_id, message)
        logger.debug(f"Broadcasted {setting_type} update to user {user_id}")

    async def broadcast_stream_info_update(self, user_id: str, platform: str, stream_info: dict):
        """Broadcast stream info update to user's connections"""
        message = {
            "type": "stream_info_updated",
            "data": {
                "platform": platform,
                "stream_info": stream_info
            }
        }
        await self.send_to_user(user_id, message)
        logger.debug(f"Broadcasted stream info update to user {user_id}")

    async def broadcast_tts_status_change(self, user_id: str, enabled: bool):
        """Broadcast TTS status change to user's connections"""
        message = {
            "type": "tts_status_changed",
            "data": {
                "enabled": enabled
            }
        }
        await self.send_to_user(user_id, message)
        logger.debug(f"Broadcasted TTS status change to user {user_id}: {enabled}")

    def register_client_connection(self, user_id: str, connection_type: str):
        """Register a client connection."""
        logger.info(f"Client connection registered: {user_id} ({connection_type})")

    def unregister_client_connection(self, user_id: str, connection_type: str):
        """Unregister a client connection."""
        logger.info(f"Client connection unregistered: {user_id} ({connection_type})")

    async def restore_active_sessions_from_db(self, db: 'Session'):
        """Restore active sessions from the database."""
        try:
            from core.database import UserSession

            # Get all active sessions.
            active_sessions = db.query(UserSession).filter(
                UserSession.is_active
            ).all()

            restored_count = 0
            for session in active_sessions:
                device_info = session.device_info or {}
                monitored_channel = device_info.get('monitored_channel')

                if monitored_channel:
                    # Add the session to the connection manager.
                    self.add_active_session(monitored_channel, session.session_id)
                    restored_count += 1
                    logger.info(
                        "Restored session %s for channel %s",
                        mask_session_id(session.session_id),
                        monitored_channel,
                    )

            logger.info(f"Restored {restored_count} active sessions from database")

        except Exception as e:
            logger.error(f"Error restoring sessions from DB: {e}")

    async def get_twitch_channels_for_bot(self, db: 'Session') -> List[str]:
        """Return Twitch channels for the bot to join."""
        try:
            # Get all channels with active Twitch tokens.
            from core.database import User, UserToken

            # Find users with active Twitch tokens.
            twitch_users = db.query(User).join(UserToken).filter(
                UserToken.platform == 'twitch',
                UserToken.is_active.is_(True),
                User.twitch_username.isnot(None)
            ).all()

            twitch_channels = []
            for user in twitch_users:
                if user.twitch_username:
                    twitch_channels.append(user.twitch_username.lower())

            logger.info(f"[GAME] Found {len(twitch_channels)} Twitch channels to listen: {twitch_channels}")
            return twitch_channels
        except Exception as e:
            logger.error(f"Error getting Twitch channels: {e}", exc_info=True)
            return []

    async def get_vk_channels_for_bot(self, db: 'Session') -> List[str]:
        """Return VK Live channels for the bot to join."""
        try:
            # Get all channels with active VK tokens.
            from core.database import User, UserToken
            from sqlalchemy import or_
            # Find users with active VK tokens.
            vk_users = db.query(User).join(UserToken).filter(
                UserToken.platform == 'vk',
                UserToken.is_active.is_(True),
                or_(User.vk_channel_name.isnot(None), User.vk_username.isnot(None))
            ).all()

            vk_channels = []
            for user in vk_users:
                # Use vk_channel_name as the primary channel identifier.
                channel_name = user.vk_channel_name or user.vk_username
                if user.vk_channel_name and user.vk_username and user.vk_channel_name.lower() != user.vk_username.lower():
                    logger.info(
                        "[VK] User %s: using vk_channel_name='%s' (vk_username='%s')",
                        user.id,
                        user.vk_channel_name,
                        user.vk_username,
                    )
                if channel_name:
                    candidate = channel_name.strip()
                    if ' ' in candidate:
                        logger.warning(f"[VK] Skipping invalid channel name with spaces: {candidate}")
                        continue
                    vk_channels.append(candidate)

            logger.info(f"Found {len(vk_channels)} VK Live channels to listen (channel slugs): {vk_channels}")
            return vk_channels
        except Exception as e:
            logger.error(f"Error getting VK channels: {e}", exc_info=True)
            return []

    async def cleanup_inactive_channels(self):
        """Clean up inactive channels."""
        try:
            removed_channels = 0
            for channel_name, sessions in list(self.active_sessions.items()):
                normalized_sessions = {session_id for session_id in sessions if str(session_id or "").strip()}
                if normalized_sessions:
                    self.active_sessions[channel_name] = normalized_sessions
                    continue

                del self.active_sessions[channel_name]
                removed_channels += 1

                for channel_key in self._channel_keys(channel_name):
                    self.tts_enabled_channels.discard(channel_key)
                    self.tts_enabled_twitch.discard(channel_key)
                    self.tts_enabled_vk.discard(channel_key)
                    self.basic_tts_enabled_channels.discard(channel_key)
                    self.ai_tts_enabled_channels.discard(channel_key)
                    self.blocked_bots.discard(channel_key)
                    self.tts_volume_settings.pop(channel_key, None)
                    self.voice_volume_settings.pop(channel_key, None)
                    self.youtube_settings.pop(channel_key, None)
                    self.youtube_queues.pop(channel_key, None)
                    self.current_videos.pop(channel_key, None)
                    self.active_vk_bots.pop(channel_key, None)

            logger.info("Inactive channel cleanup removed %s channel(s)", removed_channels)
            return removed_channels
        except Exception as e:
            logger.error(f"Error cleaning up inactive channels: {e}")
            return 0

    async def cleanup_inactive_clients(self):
        """Clean up inactive clients."""
        try:
            removed_clients = 0
            connection_maps = (
                self.active_connections,
                self.obs_connections,
                self.youtube_obs_connections,
                self.audio_connections,
            )

            for mapping in connection_maps:
                for key, websocket in list(mapping.items()):
                    if self._is_websocket_connected(websocket):
                        continue

                    mapping.pop(key, None)
                    if mapping is self.youtube_obs_connections:
                        self.youtube_obs_user_ids.pop(key, None)
                    removed_clients += 1

            logger.info("Inactive client cleanup removed %s websocket connection(s)", removed_clients)
            return removed_clients
        except Exception as e:
            logger.error(f"Error cleaning up inactive clients: {e}")
            return 0

    def cleanup(self):
        """Clean up manager resources."""
        try:
            all_websockets = (
                list(self.active_connections.values())
                + list(self.obs_connections.values())
                + list(self.youtube_obs_connections.values())
                + list(self.audio_connections.values())
            )
            for websocket in all_websockets:
                self._close_websocket_best_effort(websocket)

            self._cancel_pending_disconnects()
            self._clear_runtime_state()

            logger.info("ConnectionManager cleanup completed")
        except Exception as e:
            logger.error(f"Error during ConnectionManager cleanup: {e}")

