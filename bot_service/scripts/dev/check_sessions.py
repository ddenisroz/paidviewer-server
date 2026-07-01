#!/usr/bin/env python3
"""Diagnostic helper for active sessions and websocket connections."""

from __future__ import annotations

import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.connection_manager import get_connection_manager
from core.database import SessionLocal, User, UserSession, UserToken


def _format_device_info(device_info: object) -> str:
    if not device_info:
        return "{}"
    if isinstance(device_info, dict):
        return json.dumps(device_info, ensure_ascii=True, sort_keys=True)
    return str(device_info)


def check_sessions() -> None:
    """Print a compact diagnostic summary for session-related state."""
    print("[INFO] Inspecting active authenticated sessions and connections...")
    db = SessionLocal()

    try:
        active_sessions = (
            db.query(UserSession)
            .filter(UserSession.is_active.is_(True), UserSession.user_id.isnot(None), UserSession.user_id > 0)
            .all()
        )
        print(f"[INFO] Active authenticated DB sessions: {len(active_sessions)}")
        for session in active_sessions:
            device_info = session.device_info or {}
            channel = device_info.get("monitored_channel", "n/a") if isinstance(device_info, dict) else "n/a"
            print(f"  - user_id={session.user_id} session_id={session.session_id}")
            print(f"    channel={channel}")
            print(f"    created_at={session.created_at}")
            print(f"    device_info={_format_device_info(device_info)}")

        users_with_tokens = (
            db.query(User)
            .join(UserToken)
            .filter(UserToken.access_token.isnot(None))
            .distinct()
            .all()
        )
        print(f"[INFO] Users with stored OAuth tokens: {len(users_with_tokens)}")
        for user in users_with_tokens:
            username = user.twitch_username or user.vk_username or f"user_{user.id}"
            print(f"  - {username} (id={user.id})")
            tokens = db.query(UserToken).filter(UserToken.user_id == user.id).all()
            for token in tokens:
                print(f"    token platform={token.platform} platform_user_id={token.platform_user_id}")

        print("[INFO] Connection manager state:")
        connection_manager = get_connection_manager()
        active_channels = connection_manager.get_active_channels()
        active_sessions_dict = connection_manager.get_active_sessions()
        if not active_channels:
            print("  - no active channels")
        else:
            print(f"  - channels={active_channels}")
            for channel, sessions in active_sessions_dict.items():
                print(f"    {channel}: {len(sessions)} session(s)")

        legacy_sessions = (
            db.query(UserSession)
            .filter(UserSession.user_id == -1, UserSession.is_active.is_(True))
            .all()
        )
        print(f"[INFO] Legacy session-scoped leftovers (user_id = -1): {len(legacy_sessions)}")
        for session in legacy_sessions:
            device_info = session.device_info or {}
            channel = device_info.get("monitored_channel", "n/a") if isinstance(device_info, dict) else "n/a"
            print(f"  - session_id={session.session_id} channel={channel}")
            print(f"    device_info={_format_device_info(device_info)}")

    except Exception as exc:
        print(f"[ERROR] Failed to inspect session state: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    check_sessions()
