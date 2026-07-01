# bot_service/services/memory_websocket_manager.py
"""
In-memory WebSocket manager.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass
class WebSocketConnection:
    """Information about a websocket connection."""

    websocket: WebSocket
    user_id: int
    channel: str
    platform: str
    connected_at: float
    last_ping: float
    is_active: bool = True
    name: str = ""
    client_role: str = "dashboard"
    presence_only: bool = False


class MemoryWebSocketManager:
    """In-memory WebSocket manager."""

    def __init__(self):
        self.connections: Dict[str, WebSocketConnection] = {}
        self.user_connections: Dict[int, Set[str]] = {}
        self.channel_connections: Dict[str, Set[str]] = {}
        self._running = False
        self._ping_interval = 30
        self._ping_task: Optional[asyncio.Task] = None
        self._last_server_ping: Dict[str, float] = {}

    async def start(self):
        """Start manager."""
        if self._running:
            return

        self._running = True
        self._ping_task = asyncio.create_task(self._ping_loop())
        logger.info("Memory WebSocket Manager started")

    async def stop(self):
        """Stop manager."""
        self._running = False

        if self._ping_task:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass

        for conn_id, connection in list(self.connections.items()):
            try:
                await connection.websocket.close()
            except Exception as error:
                logger.error("Error closing WebSocket %s: %s", conn_id, error)

        self.connections.clear()
        self.user_connections.clear()
        self.channel_connections.clear()

        logger.info("Memory WebSocket Manager stopped")

    @staticmethod
    def _normalize_client_role(client_role: Optional[str]) -> str:
        role = (client_role or "dashboard").strip().lower()
        return role or "dashboard"

    async def add_connection(
        self,
        websocket: WebSocket,
        user_id: int,
        channel: str,
        platform: str = "twitch",
        client_role: str = "dashboard",
        presence_only: bool = False
    ) -> str:
        """
        Add websocket connection.

        Returns:
            str: connection id
        """
        role = self._normalize_client_role(client_role)
        now = time.time()
        conn_id = f"{user_id}_{channel}_{platform}_{role}_{time.time_ns()}"

        connection = WebSocketConnection(
            websocket=websocket,
            user_id=user_id,
            channel=channel,
            platform=platform,
            connected_at=now,
            last_ping=now,
            name=channel,
            client_role=role,
            presence_only=presence_only
        )

        self.connections[conn_id] = connection

        if user_id not in self.user_connections:
            self.user_connections[user_id] = set()
        self.user_connections[user_id].add(conn_id)

        if channel not in self.channel_connections:
            self.channel_connections[channel] = set()
        self.channel_connections[channel].add(conn_id)

        if role == "tts_player":
            await self.sync_user_tts_generation(user_id)

        logger.info(
            "WebSocket connection added: %s (role=%s, presence_only=%s)",
            conn_id,
            role,
            presence_only,
        )
        return conn_id

    async def remove_connection(self, conn_id: str):
        """Remove websocket connection."""
        if conn_id not in self.connections:
            return

        connection = self.connections[conn_id]
        user_id = connection.user_id

        if user_id in self.user_connections:
            self.user_connections[user_id].discard(conn_id)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]

        if connection.channel in self.channel_connections:
            self.channel_connections[connection.channel].discard(conn_id)
            if not self.channel_connections[connection.channel]:
                del self.channel_connections[connection.channel]

        del self.connections[conn_id]
        self._last_server_ping.pop(conn_id, None)

        if connection.client_role == "tts_player":
            await self.sync_user_tts_generation(user_id)
            await self._schedule_tts_disconnect_if_needed(user_id)

        logger.info("WebSocket connection removed: %s", conn_id)

    async def _schedule_tts_disconnect_if_needed(self, user_id: int) -> None:
        """
        Ensure delayed TTS shutdown is scheduled when user has no active websocket connections.
        This covers non-graceful disconnect paths (ping timeout/network drops).
        """
        if self.is_user_connected(user_id):
            return

        try:
            from core.connection_manager import get_connection_manager
            from core.database import User, get_db

            conn_mgr = get_connection_manager()
            pending = conn_mgr.pending_tts_disconnects.get(user_id)
            if pending and not pending.done():
                return

            db = next(get_db())
            try:
                user = db.query(User).filter(User.id == user_id).first()
                if not user:
                    return
                username = user.twitch_username or user.vk_username or user.vk_channel_name or f"user_{user_id}"
                conn_mgr.schedule_tts_disconnect(user_id, username)
                logger.info(
                    "Scheduled TTS disconnect after last WebSocket removal for user %s (%s)",
                    user_id,
                    username,
                )
            finally:
                db.close()
        except Exception as error:
            logger.error("Failed to schedule TTS disconnect for user %s: %s", user_id, error)

    async def send_to_user(
        self,
        user_id: int,
        message: Dict[str, Any],
        client_roles: Optional[Set[str]] = None,
        exclude_presence_only: bool = False
    ) -> int:
        """
        Send message to user.

        Returns:
            int: number of successful deliveries
        """
        if user_id not in self.user_connections:
            return 0

        allowed_roles = {self._normalize_client_role(role) for role in (client_roles or set())}
        sent_count = 0

        for conn_id in list(self.user_connections[user_id]):
            connection = self.connections.get(conn_id)
            if not connection:
                continue

            if not connection.is_active:
                continue

            if allowed_roles and connection.client_role not in allowed_roles:
                continue

            if exclude_presence_only and connection.presence_only:
                continue

            try:
                await connection.websocket.send_json(message)
                sent_count += 1
            except Exception as error:
                logger.error("Error sending message to user %s: %s", user_id, error)
                await self.remove_connection(conn_id)

        return sent_count

    async def send_to_channel(self, channel: str, message: Dict[str, Any]):
        """Send message to channel."""
        if channel not in self.channel_connections:
            return

        for conn_id in list(self.channel_connections[channel]):
            try:
                connection = self.connections.get(conn_id)
                if connection and connection.is_active:
                    await connection.websocket.send_json(message)
            except Exception as error:
                logger.error("Error sending message to channel %s: %s", channel, error)
                await self.remove_connection(conn_id)

    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast message to all active connections."""
        for conn_id, connection in list(self.connections.items()):
            try:
                if connection.is_active:
                    await connection.websocket.send_json(message)
            except Exception as error:
                logger.error("Error broadcasting message: %s", error)
                await self.remove_connection(conn_id)

    async def broadcast_to_all(self, message: str):
        """Broadcast text payload to all active connections."""
        disconnected: List[str] = []
        for conn_id, connection in list(self.connections.items()):
            try:
                if connection.is_active:
                    await connection.websocket.send_text(message)
            except Exception as error:
                logger.error("Error broadcasting message to all: %s", error)
                disconnected.append(conn_id)

        for conn_id in disconnected:
            await self.remove_connection(conn_id)

    async def handle_ping(self, conn_id: str):
        """Handle ping from client."""
        if conn_id in self.connections:
            connection = self.connections[conn_id]
            connection.last_ping = time.time()
            try:
                await connection.websocket.send_json({"type": "pong"})
            except Exception as error:
                logger.error("Error sending pong to %s: %s", conn_id, error)
                await self.remove_connection(conn_id)

    async def _ping_loop(self):
        """Connection health check loop."""
        while self._running:
            try:
                current_time = time.time()
                inactive_connections: List[str] = []

                for conn_id, connection in list(self.connections.items()):
                    if not connection.is_active:
                        continue

                    time_since_last_ping = current_time - connection.last_ping
                    if time_since_last_ping > 60:
                        logger.warning("Connection %s inactive for %ss, removing", conn_id, time_since_last_ping)
                        inactive_connections.append(conn_id)
                        continue

                    last_server_ping = self._last_server_ping.get(conn_id, 0.0)
                    if (
                        time_since_last_ping > self._ping_interval
                        and (current_time - last_server_ping) >= self._ping_interval
                    ):
                        try:
                            await connection.websocket.send_json({"type": "ping"})
                            self._last_server_ping[conn_id] = current_time
                        except Exception as error:
                            logger.warning("Ping failed for %s: %s", conn_id, error)
                            inactive_connections.append(conn_id)

                for conn_id in inactive_connections:
                    await self.remove_connection(conn_id)

                await asyncio.sleep(5)

            except Exception as error:
                logger.error("Error in ping loop: %s", error)
                await asyncio.sleep(5)

    def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection stats."""
        active_connections = sum(1 for conn in self.connections.values() if conn.is_active)
        total_connections = len(self.connections)
        unique_users = len(self.user_connections)
        unique_channels = len(self.channel_connections)

        return {
            "active_connections": active_connections,
            "total_connections": total_connections,
            "unique_users": unique_users,
            "unique_channels": unique_channels,
            "running": self._running,
        }

    def get_user_connections(self, user_id: int) -> List[Dict[str, Any]]:
        """Get user connections."""
        if user_id not in self.user_connections:
            return []

        connections: List[Dict[str, Any]] = []
        for conn_id in self.user_connections[user_id]:
            connection = self.connections.get(conn_id)
            if connection:
                connections.append({
                    "conn_id": conn_id,
                    "channel": connection.channel,
                    "platform": connection.platform,
                    "connected_at": connection.connected_at,
                    "is_active": connection.is_active,
                    "client_role": connection.client_role,
                    "presence_only": connection.presence_only,
                })

        return connections

    def is_user_connected(self, user_id: int) -> bool:
        """Check whether user has at least one active connection."""
        if user_id not in self.user_connections:
            return False

        for conn_id in self.user_connections[user_id]:
            connection = self.connections.get(conn_id)
            if connection and connection.is_active:
                return True

        return False

    def has_user_connection_for_role(self, user_id: int, client_role: str) -> bool:
        """Check whether user has active connection for a role."""
        target_role = self._normalize_client_role(client_role)

        if user_id not in self.user_connections:
            return False

        for conn_id in self.user_connections[user_id]:
            connection = self.connections.get(conn_id)
            if connection and connection.is_active and connection.client_role == target_role:
                return True

        return False

    @staticmethod
    def _has_active_obs_sink(user: Any) -> bool:
        """
        Check whether user currently has an active OBS websocket sink.
        """
        source_token = getattr(user, "tts_source_token", None)
        legacy_token = getattr(user, "obs_token", None)
        tokens = [token for token in (source_token, legacy_token) if token]
        if not tokens:
            return False

        try:
            from core.connection_manager import get_connection_manager

            connection_manager = get_connection_manager()
            return any(token in connection_manager.obs_connections for token in tokens)
        except Exception as error:
            logger.debug("Failed to resolve OBS sink state: %s", error)
            return False

    async def _should_enable_tts_generation(self, user_id: int) -> bool:
        """
        Determine whether TTS generation should be enabled for a user.

        Rules:
        - If TTS is disabled in user settings -> disabled.
        - If listening mode is `obs` -> enabled only with active OBS websocket sink.
        - If listening mode is `website` -> enabled only with active `tts_player` connection.
        """
        from core.database import get_db, User
        from models.tts import TTSUserSettings

        db = next(get_db())
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.debug("TTS generation disabled for user %s: user_not_found", user_id)
                return False

            if not getattr(user, "tts_enabled", False):
                logger.debug("TTS generation disabled for user %s: tts_disabled", user_id)
                return False

            listening_mode = getattr(user, "tts_listening_mode", "website")
            tts_settings = db.query(TTSUserSettings).filter(TTSUserSettings.user_id == user_id).first()
            if tts_settings and getattr(tts_settings, "listening_mode", None) in {"website", "obs"}:
                listening_mode = tts_settings.listening_mode

            if listening_mode == "obs":
                has_sink = self._has_active_obs_sink(user)
                logger.debug(
                    "TTS generation decision for user %s: mode=obs source_connected=%s",
                    user_id,
                    has_sink,
                )
                return has_sink

            if listening_mode == "website":
                has_player = self.has_user_connection_for_role(user_id, "tts_player")
                logger.debug(
                    "TTS generation decision for user %s: mode=website player_connected=%s",
                    user_id,
                    has_player,
                )
                return has_player

            logger.debug("TTS generation disabled for user %s: unsupported_mode=%s", user_id, listening_mode)
            return False
        finally:
            db.close()

    async def sync_user_tts_generation(self, user_id: int):
        """Sync user TTS generation state with current websocket presence and listening mode."""
        try:
            from services.tts.memory_tts_queue import get_memory_tts_queue

            should_enable = await self._should_enable_tts_generation(user_id)
            queue = get_memory_tts_queue()

            if should_enable:
                await queue.enable_for_user(user_id)
                logger.debug("TTS generation enabled for user %s", user_id)
            else:
                await queue.disable_for_user(user_id)
                logger.debug("TTS generation disabled for user %s", user_id)
        except Exception as error:
            logger.error("Error syncing TTS generation for user %s: %s", user_id, error)


_memory_websocket_manager: Optional[MemoryWebSocketManager] = None


def get_memory_websocket_manager() -> MemoryWebSocketManager:
    """Get or create global MemoryWebSocketManager."""
    global _memory_websocket_manager
    if _memory_websocket_manager is None:
        _memory_websocket_manager = MemoryWebSocketManager()
    return _memory_websocket_manager

