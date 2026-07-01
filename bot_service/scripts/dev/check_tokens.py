#!/usr/bin/env python3
"""Check OAuth tokens stored in the database."""
import sys
import os
from datetime import datetime
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.database import get_db, UserToken
from core.datetime_utils import utcnow_naive

def check_tokens():
    print('=' * 80)
    print('Checking tokens in the database')
    print('=' * 80)
    print()
    db = next(get_db())
    try:
        tokens = db.query(UserToken).all()
        if not tokens:
            print('[ERROR] No tokens found in the database')
            print()
            print('What to do:')
            print('1. Open http://localhost:5173')
            print('2. Active platform tokens')
            print('3. Connect platforms (Twitch, VK Live, DonationAlerts)')
            print()
            return
        print(f'Tokens found: {len(tokens)}')
        print()
        now = utcnow_naive()
        for token in tokens:
            print(f'[LIST] Platform: {token.platform.upper()}')
            print(f'   User ID: {token.user_id}')
            print(f'   Platform User ID: {token.platform_user_id}')
            print(f"   Platform Username: {token.platform_username or 'N/A'}")
            print(f"   Access Token: {('[OK]' if token.access_token else '[X]')}")
            print(f"   Refresh Token: {('[OK]' if token.refresh_token else '[X]')}")
            if token.expires_at:
                expires_in = token.expires_at - now
                expires_str = f'{expires_in.days} days {expires_in.seconds // 3600} hours'
                if expires_in.total_seconds() > 0:
                    print(f'   Expires at: {token.expires_at} ({expires_str})')
                    print('   Status: [OK] Valid')
                else:
                    print(f'   Expires at: {token.expires_at} (expired {expires_str} ago)')
                    print('   Status: [WARN] Expired')
                    if token.refresh_token:
                        print('   Refresh: [OK] Can be refreshed')
                    else:
                        print('   Refresh: [X] Reauthorization required')
            else:
                print(f'   Expires at: N/A')
                print('   Status: [WARN] No expiration date set')
            print()
        print('=' * 80)
        print()
        vk_tokens = [t for t in tokens if t.platform == 'vk']
        if vk_tokens:
            print('[OK] VK Live token found in the database')
            vk_token = vk_tokens[0]
            if vk_token.refresh_token:
                print('[OK] Refresh token is available: auto-refresh is enabled')
            else:
                print('[WARN] Refresh token is missing: reauthorization required')
        else:
            print('[ERROR] VK Live token not found in the database')
            print('   -> Connect VK Live through the dashboard')
        print()
    except Exception as e:
        print(f'[ERROR] Failed to inspect tokens: {e}')
        import traceback
        traceback.print_exc()
    finally:
        db.close()
if __name__ == '__main__':
    check_tokens()
