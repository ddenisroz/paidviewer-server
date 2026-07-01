"""Check Twitch bot OAuth token status."""
import sys
import os
import asyncio
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.database import db_session
from services.twitch_bot_oauth_service import twitch_bot_oauth_service

async def check_bot_token():
    """Check the configured bot token."""
    print('\n' + '=' * 60)
    print('Checking OAuth token for Twitch bot')
    print('=' * 60 + '\n')
    with db_session() as db:
        bot_token = await twitch_bot_oauth_service.get_bot_token(db)
        if not bot_token:
            print('[ERROR] Bot token is not configured')
            print('\nTo configure it:')
            print('1. Open the admin panel: http://localhost:5173/settings')
            print("2. Click 'Authorize bot'")
            print('3. Sign in with the Twitch bot account')
            return
        print('[OK] Bot token is configured\n')
        print(f"Bot login:      {bot_token.get('bot_login', 'N/A')}")
        print(f"Bot user ID:    {bot_token.get('bot_user_id', 'N/A')}")
        expires_at = bot_token.get('expires_at')
        if expires_at:
            now = datetime.utcnow()
            days_left = (expires_at - now).days
            hours_left = (expires_at - now).seconds // 3600
            print(f"\nExpires at:     {expires_at.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            print(f'Remaining:      {days_left} days, {hours_left} hours')
            if days_left < 1:
                print('[WARN] Token expires soon')
            elif days_left < 7:
                print('[WARN] Token should be refreshed soon')
            else:
                print('[OK] Token is valid')
        else:
            print('\nExpires at:     not set')
        has_refresh = bool(bot_token.get('refresh_token'))
        print(
            f"\nRefresh token:  "
            f"{('available (auto-refresh works)' if has_refresh else '[ERROR] missing (auto-refresh unavailable)')}"
        )
        if not has_refresh:
            print('\n[WARN] To enable auto-refresh:')
            print('1. Open the admin panel: http://localhost:5173/settings')
            print("2. Click 'Reauthorize'")
            print('3. Sign in with the Twitch bot account')
        print('\n' + '=' * 60 + '\n')
if __name__ == '__main__':
    asyncio.run(check_bot_token())
