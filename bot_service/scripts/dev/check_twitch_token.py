#!/usr/bin/env python3
"""
Check dedicated Twitch bot OAuth token status from DB.

Usage:
    python scripts/check_twitch_token.py
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import SessionLocal
from services.bot_token_validator import bot_token_validator
from services.twitch_bot_oauth_service import twitch_bot_oauth_service


async def main() -> int:
    print("=" * 80)
    print("TWITCH BOT OAUTH TOKEN CHECK (DB)")
    print("=" * 80)

    db = SessionLocal()
    try:
        token_data = await twitch_bot_oauth_service.get_bot_token(db)
    finally:
        db.close()

    if not token_data:
        print("[ERROR] No Twitch bot OAuth token in DB.")
        print("Fix: open http://localhost:8000/auth/twitch/bot/login as app admin.")
        return 1

    print(f"[OK] DB token found for bot login: {token_data.get('bot_login')}")
    if token_data.get("expires_at"):
        print(f"[INFO] Expires at: {token_data['expires_at']}")
    else:
        print("[WARN] Token expiration is not set.")

    validation = await bot_token_validator.validate_twitch_bot_token()
    if validation.get("valid"):
        print("[OK] Twitch bot token is valid.")
        print(f"[INFO] login={validation.get('login')} user_id={validation.get('user_id')}")
        return 0

    print("[ERROR] Twitch bot token is invalid.")
    print(f"[ERROR] reason={validation.get('error')}")
    print("Fix: re-authorize bot via /auth/twitch/bot/login")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

