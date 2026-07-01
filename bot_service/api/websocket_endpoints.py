# bot_service/api/websocket_endpoints.py
"""
WebSocket endpoints for chat and diagnostics.

Moved out of main.py to improve modularity.
"""

import json
import asyncio
import logging
from typing import List, Dict, Any, Optional, Iterable

from fastapi import APIRouter, WebSocket, HTTPException

from core.config import settings
from core.database import ChatMessage, get_db
from core.connection_manager import get_connection_manager
from core.session_manager import session_manager
from services.memory_websocket_manager import get_memory_websocket_manager
from repositories.chatbox_repository import ChatBoxRepository
from repositories.user_repository import UserRepository
from auth.auth import verify_jwt_token
from services.notification_service import notification_service
from services.youtube.obs_overlay import build_youtube_obs_state

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


async def _load_chat_history(user_id: int) -> List[Dict[str, Any]]:
    """
    Load chat history for a user.
    """
    def _db_query():
        # Use the session context manager when available, otherwise read the session directly.
        # In this project, get_db() is implemented as a generator.
        db = next(get_db())
        try:
            from repositories.user_repository import UserRepository
            from repositories.chat_message_repository import ChatMessageRepository
            
            user_repo = UserRepository(db)
            user = user_repo.get_by_id(user_id)
            if not user:
                return []
            
            platforms = []
            if user.twitch_username:
                platforms.append("twitch")
            if user.vk_channel_name:
                platforms.append("vk")

            if not platforms:
                return []
            
            chat_repo = ChatMessageRepository(db)
            # Optimization: limit=20 for faster initial load; the client can request more if needed.
            messages = chat_repo.get_history_by_platforms(user_id, platforms, limit=20)
            messages.sort(key=lambda x: x.timestamp)
            return messages
        except Exception:
            logger.exception("Error querying chat history")
            return []
        finally:
            db.close()
    
    return await asyncio.to_thread(_db_query)


def _format_message(msg: ChatMessage) -> Dict[str, Any]:
    """Format a chat message for client delivery."""
    # Parse badges
    badges_list = msg.badges
    if isinstance(badges_list, str):
        try:
            badges_list = json.loads(badges_list)
        except (json.JSONDecodeError, TypeError):
            badges_list = None
    
    # Convert the timestamp
    timestamp_ms = None
    if msg.timestamp:
        timestamp_ms = int(msg.timestamp.timestamp() * 1000)
    
    return {
        "id": msg.id,
        "platform": msg.platform,
        "author": msg.author_username,
        "author_name": msg.author_username,
        "message": msg.message,
        "timestamp": timestamp_ms,
        "channel": msg.channel_name,
        "role": msg.role,
        "badges": badges_list
    }


async def _send_chat_history(websocket: WebSocket, user_id: int) -> None:
    """
    Send chat history over WebSocket.
    
    Runs asynchronously in the background.
    """
    try:
        await asyncio.sleep(0.05)  # Give the client time to initialize
        
        messages = await _load_chat_history(user_id)
        
        if not messages:
            return
        
        history_data = [_format_message(msg) for msg in messages]
        
        await websocket.send_text(json.dumps({
            "type": "chat_history",
            "messages": history_data
        }))
        
        logger.info(f"[HISTORY] Sent {len(history_data)} messages")
        
    except Exception:
        logger.exception("[WARN] Error loading chat history")


async def _resolve_authenticated_user_id(websocket: WebSocket) -> Optional[int]:
    """Resolve authenticated user_id from WebSocket token or session cookie."""
    ws_token = (websocket.query_params.get("ws_token") or "").strip()
    if ws_token:
        try:
            payload = verify_jwt_token(ws_token, expected_type="chat_ws")
            raw_user_id = payload.get("user_id")
            user_id = int(raw_user_id) if raw_user_id else 0
            if user_id > 0:
                return user_id
        except Exception:
            return None

    obs_token = (websocket.query_params.get("obs_token") or "").strip()
    if obs_token:
        client_role = (websocket.query_params.get("client_role") or "").strip().lower()
        presence_only_raw = websocket.query_params.get("presence_only")
        presence_only = str(presence_only_raw).strip().lower() in {"1", "true", "yes", "on"}
        if client_role == "tts_player" and presence_only:
            return _resolve_jwt_token_user_id(obs_token, ("tts_dock", "obs"))

    session_id = websocket.cookies.get("session_id")
    if not session_id:
        return None

    session_data = await asyncio.to_thread(session_manager.validate_session, session_id)
    if not session_data or session_data.get("is_blocked"):
        return None

    raw_user_id = session_data.get("id") or session_data.get("user_id")
    try:
        user_id = int(raw_user_id)
    except (TypeError, ValueError):
        return None

    if user_id <= 0:
        return None

    return user_id


async def _resolve_dev_tts_player_user_id(websocket: WebSocket, path_user_id: int) -> Optional[int]:
    """Local-only fallback for the dedicated TTS player during development."""
    if not settings.is_development:
        return None

    client_role = (websocket.query_params.get("client_role") or "").strip().lower()
    presence_only_raw = websocket.query_params.get("presence_only")
    presence_only = str(presence_only_raw).strip().lower() in {"1", "true", "yes", "on"}
    origin = (websocket.headers.get("origin") or "").strip().lower()

    if client_role != "tts_player" or not presence_only:
        return None

    if origin and "localhost" not in origin and "127.0.0.1" not in origin:
        return None

    def _db_query() -> bool:
        db = next(get_db())
        try:
            return UserRepository(db).get_by_id(path_user_id) is not None
        finally:
            db.close()

    user_exists = await asyncio.to_thread(_db_query)
    if not user_exists:
        return None

    logger.info("[WS] Development fallback accepted for TTS player user_id=%s", path_user_id)
    return path_user_id


async def _resolve_chatbox_token_user_id(token: str) -> Optional[int]:
    """Resolve a public OBS ChatBox token to its owner user_id."""
    cleaned_token = (token or "").strip()
    if not cleaned_token:
        return None

    def _db_query() -> Optional[int]:
        db = next(get_db())
        try:
            settings_row = ChatBoxRepository(db).get_by_token(cleaned_token)
            if not settings_row:
                return None
            return int(settings_row.user_id)
        finally:
            db.close()

    return await asyncio.to_thread(_db_query)


async def _resolve_drops_widget_token_user_id(token: str) -> Optional[int]:
    """Resolve a public OBS drops widget token to its owner user_id."""
    cleaned_token = (token or "").strip()
    if not cleaned_token:
        return None

    def _db_query() -> Optional[int]:
        db = next(get_db())
        try:
            from repositories.drops_config_repository import DropsConfigRepository

            config = DropsConfigRepository(db).get_by_widget_token(cleaned_token)
            if not config or not config.user_id:
                return None
            return int(config.user_id)
        finally:
            db.close()

    return await asyncio.to_thread(_db_query)


async def _run_chat_connection(
    websocket: WebSocket,
    user_id_int: int,
    *,
    client_role: str,
    presence_only: bool,
    display_user_id: str,
    manage_tts_disconnect: bool,
) -> None:
    """Run the shared chat websocket loop after auth/token validation."""
    await websocket.accept()

    manager = get_memory_websocket_manager()
    conn_mgr = get_connection_manager()

    if manage_tts_disconnect:
        conn_mgr.cancel_tts_disconnect(user_id_int)

    conn_id = await manager.add_connection(
        websocket,
        user_id_int,
        f"user_{user_id_int}",
        "chat",
        client_role=client_role,
        presence_only=presence_only,
    )
    logger.info(
        "[WS] Connected: %s (User: %s, role=%s, presence_only=%s)",
        conn_id,
        display_user_id,
        client_role,
        presence_only,
    )

    history_task: asyncio.Task | None = None
    if not presence_only:
        history_task = asyncio.create_task(_send_chat_history(websocket, user_id_int))

    try:
        while True:
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                continue

            if message.get("type") == "ping":
                await manager.handle_ping(conn_id)
                continue

            if client_role == "tts_player" and message.get("type") == "tts_control":
                await _send_tts_control_to_source(user_id_int, str(message.get("command") or ""))
                continue

            # Keep non-heartbeat client chatter out of warning/error logs.
            msg_type = message.get("type", "unknown")
            if msg_type != "pong":
                logger.debug("[WS] User %s sent: %s", display_user_id, msg_type)

    except Exception as e:
        e_str = str(e)
        if "1000" in e_str or "1001" in e_str or "closed" in e_str.lower():
            logger.info("[WS] Disconnected cleanly: %s", display_user_id)
        else:
            logger.warning("[WS] Error user %s: %s", display_user_id, e)

    finally:
        if history_task and not history_task.done():
            history_task.cancel()

        await manager.remove_connection(conn_id)

        if not manage_tts_disconnect:
            return

        remaining = manager.get_user_connections(user_id_int)
        if not remaining:
            pending = conn_mgr.pending_tts_disconnects.get(user_id_int)
            if pending and not pending.done():
                logger.debug(
                    "[WS] TTS disconnect already scheduled for %s, skipping duplicate schedule",
                    display_user_id,
                )
            else:
                logger.info(
                    "[WS] No active connections for %s, scheduling TTS disconnect",
                    display_user_id,
                )
                await _schedule_tts_disconnect(user_id_int)
        else:
            logger.debug(
                "[WS] User %s still has %s connections, skipping disconnect timer",
                display_user_id,
                len(remaining),
            )


@router.websocket("/ws/chat/{user_id}")
async def websocket_chat(websocket: WebSocket, user_id: str):
    """
    WebSocket endpoint for chat.
    """
    logger.info(f"[WS] Connection request for user {user_id}")

    user_id_int = int(user_id) if user_id.isdigit() else -1
    if user_id_int <= 0:
        logger.warning(f"[WS] Invalid user_id {user_id}, closing")
        await websocket.close(code=4400)
        return

    authenticated_user_id = await _resolve_authenticated_user_id(websocket)
    if not authenticated_user_id:
        authenticated_user_id = await _resolve_dev_tts_player_user_id(websocket, user_id_int)
    if not authenticated_user_id:
        logger.warning("[WS] Unauthorized connection attempt: missing/invalid session")
        await websocket.close(code=4401)
        return

    if authenticated_user_id != user_id_int:
        logger.warning(
            "[WS] Forbidden connection attempt: session user_id=%s path user_id=%s",
            authenticated_user_id,
            user_id_int,
        )
        await websocket.close(code=4403)
        return

    client_role = (websocket.query_params.get("client_role") or "dashboard").strip().lower()
    presence_only_raw = websocket.query_params.get("presence_only")
    presence_only = str(presence_only_raw).strip().lower() in {"1", "true", "yes", "on"}

    await _run_chat_connection(
        websocket,
        user_id_int,
        client_role=client_role,
        presence_only=presence_only,
        display_user_id=user_id,
        manage_tts_disconnect=True,
    )


@router.websocket("/ws/chat-overlay/{token}")
async def websocket_chat_overlay(websocket: WebSocket, token: str):
    """Token-scoped OBS chat overlay websocket; no session cookie required."""
    token_preview = (token or "")[:8]
    logger.info("[WS] Overlay connection request for token %s...", token_preview)

    user_id_int = await _resolve_chatbox_token_user_id(token)
    if not user_id_int:
        logger.warning("[WS] Invalid chat overlay token %s..., closing", token_preview)
        await websocket.close(code=4401)
        return

    await _run_chat_connection(
        websocket,
        user_id_int,
        client_role="overlay",
        presence_only=False,
        display_user_id=f"overlay:{user_id_int}",
        manage_tts_disconnect=False,
    )


@router.websocket("/ws/drops-widget/{token}")
async def websocket_drops_widget(websocket: WebSocket, token: str):
    """Token-scoped OBS drops widget websocket; no session cookie required."""
    token_preview = (token or "")[:8]
    logger.info("[WS] Drops widget connection request for token %s...", token_preview)

    user_id_int = await _resolve_drops_widget_token_user_id(token)
    if not user_id_int:
        logger.warning("[WS] Invalid drops widget token %s..., closing", token_preview)
        await websocket.close(code=4401)
        return

    await _run_chat_connection(
        websocket,
        user_id_int,
        client_role="drops_widget",
        presence_only=True,
        display_user_id=f"drops-widget:{user_id_int}",
        manage_tts_disconnect=False,
    )


def _resolve_jwt_token_user_id(token: str, expected_types: Iterable[str]) -> Optional[int]:
    for expected_type in expected_types:
        try:
            payload = verify_jwt_token(token, expected_type=expected_type)
            user_id = payload.get("user_id")
            parsed_user_id = int(user_id) if user_id else 0
            if parsed_user_id > 0:
                return parsed_user_id
        except (HTTPException, TypeError, ValueError):
            continue
    return None


def _resolve_obs_token_user_id(token: str) -> Optional[int]:
    return _resolve_jwt_token_user_id(token, ("obs",))


def _resolve_tts_source_token_user_id(token: str) -> Optional[int]:
    return _resolve_jwt_token_user_id(token, ("tts_source", "obs"))


def _resolve_tts_dock_token_user_id(token: str) -> Optional[int]:
    return _resolve_jwt_token_user_id(token, ("tts_dock", "obs"))


async def _send_tts_control_to_source(user_id: int, command: str) -> bool:
    normalized_command = command.strip().lower()
    if normalized_command not in {"start", "stop", "skip", "clear"}:
        return False

    def _db_query() -> tuple[str | None, str | None]:
        db = next(get_db())
        try:
            user = UserRepository(db).get_by_id(user_id)
            if not user:
                return None, None
            return getattr(user, "tts_source_token", None), getattr(user, "obs_token", None)
        finally:
            db.close()

    source_token, legacy_token = await asyncio.to_thread(_db_query)
    connection_manager = get_connection_manager()
    for token in (source_token, legacy_token):
        if not token:
            continue
        source_socket = connection_manager.obs_connections.get(token)
        if not source_socket:
            continue
        try:
            await source_socket.send_json({"type": "tts_control", "command": normalized_command})
            return True
        except Exception:
            logger.warning("[WS] Failed to relay TTS control command=%s user=%s", normalized_command, user_id)
    return False


async def _load_youtube_obs_state(user_id: int) -> Dict[str, Any]:
    def _db_query() -> Dict[str, Any]:
        db = next(get_db())
        try:
            return build_youtube_obs_state(user_id, db)
        finally:
            db.close()

    return await asyncio.to_thread(_db_query)


@router.websocket("/ws/youtube-obs/{token}")
async def websocket_youtube_obs(websocket: WebSocket, token: str):
    """Public OBS websocket for YouTube overlay state."""
    token_preview = (token or "")[:8]
    user_id = _resolve_obs_token_user_id(token)
    if not user_id:
        logger.warning("[WS] Invalid YouTube OBS token %s..., closing", token_preview)
        await websocket.close(code=4401)
        return

    conn_mgr = get_connection_manager()
    await conn_mgr.connect_youtube_obs(websocket, token, user_id)

    try:
        await websocket.send_json(
            {
                "type": "youtube_obs_state",
                "data": await _load_youtube_obs_state(user_id),
            }
        )

        while True:
            raw_message = await websocket.receive_text()
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                continue

            message_type = message.get("type")
            if message_type == "ping":
                await websocket.send_json({"type": "pong"})
            elif message_type in {"refresh", "request_state"}:
                await websocket.send_json(
                    {
                        "type": "youtube_obs_state",
                        "data": await _load_youtube_obs_state(user_id),
                    }
                )

    except Exception as exc:
        exc_text = str(exc).lower()
        if "1000" in exc_text or "1001" in exc_text or "disconnect" in exc_text or "closed" in exc_text:
            logger.info("[WS] YouTube OBS disconnected cleanly: user=%s", user_id)
        else:
            logger.warning("[WS] YouTube OBS error for user %s: %s", user_id, exc)
    finally:
        await conn_mgr.disconnect_youtube_obs(token)


@router.websocket("/ws/tts/{token}")
async def websocket_tts_obs(websocket: WebSocket, token: str):
    """Public OBS browser-source websocket for TTS audio playback."""
    token_preview = (token or "")[:8]
    user_id = _resolve_tts_source_token_user_id(token)
    if not user_id:
        logger.warning("[WS] Invalid TTS OBS token %s..., closing", token_preview)
        await websocket.close(code=4401)
        return

    conn_mgr = get_connection_manager()
    await conn_mgr.connect_obs(websocket, token)

    try:
        while True:
            raw_message = await websocket.receive_text()
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                continue

            message_type = message.get("type")
            if message_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if message_type == "tts_status":
                await notification_service.broadcast_tts_status(
                    user_id=user_id,
                    source_message_id=message.get("source_message_id"),
                    status=message.get("status") or "queued",
                    reason_code=message.get("reason_code"),
                )

    except Exception as exc:
        exc_text = str(exc).lower()
        if "1000" in exc_text or "1001" in exc_text or "disconnect" in exc_text or "closed" in exc_text:
            logger.info("[WS] TTS OBS disconnected cleanly: user=%s", user_id)
        else:
            logger.warning("[WS] TTS OBS error for user %s: %s", user_id, exc)
    finally:
        await conn_mgr.disconnect_obs(token)


@router.websocket("/ws/tts-dock/{token}")
async def websocket_tts_dock(websocket: WebSocket, token: str):
    """Public OBS dock control websocket for TTS queue controls."""
    token_preview = (token or "")[:8]
    user_id = _resolve_tts_dock_token_user_id(token)
    if not user_id:
        logger.warning("[WS] Invalid TTS dock token %s..., closing", token_preview)
        await websocket.close(code=4401)
        return

    await websocket.accept()
    try:
        await websocket.send_json({"type": "tts_dock_state", "data": {"user_id": user_id}})
        while True:
            raw_message = await websocket.receive_text()
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                continue

            message_type = message.get("type")
            if message_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if message_type in {"tts_control", "control"}:
                command = str(message.get("command") or "").strip().lower()
                relayed = await _send_tts_control_to_source(user_id, command)
                await websocket.send_json(
                    {"type": "tts_control_ack", "command": command, "relayed": relayed}
                )
    except Exception as exc:
        exc_text = str(exc).lower()
        if "1000" in exc_text or "1001" in exc_text or "disconnect" in exc_text or "closed" in exc_text:
            logger.info("[WS] TTS dock disconnected cleanly: user=%s", user_id)
        else:
            logger.warning("[WS] TTS dock error for user %s: %s", user_id, exc)


async def _schedule_tts_disconnect(user_id: int) -> None:
    """Schedule TTS shutdown after user disconnect."""
    conn_mgr = get_connection_manager()
    
    db = next(get_db())
    try:
        user_repo = UserRepository(db)
        user = user_repo.get_by_id(user_id)
        
        if user:
            username = user.twitch_username or user.vk_username or f"user_{user_id}"
            conn_mgr.schedule_tts_disconnect(user_id, username)
        else:
            logger.warning(f"[WARN] User {user_id} not found, skipping TTS disconnect")
    finally:
        db.close()


@router.websocket("/ws/test")
async def websocket_test(websocket: WebSocket):
    """Diagnostic WebSocket endpoint."""
    if settings.is_production:
        await websocket.close(code=4403)
        return

    logger.info("[WS] Test WebSocket connection attempt")
    await websocket.accept()
    logger.info("[OK] Test WebSocket connected")
    
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"[WS] Test received: {data}")
            await websocket.send_text(f"Echo: {data}")
    except Exception:
        logger.exception("[ERROR] Test WebSocket error")
        await websocket.close()
