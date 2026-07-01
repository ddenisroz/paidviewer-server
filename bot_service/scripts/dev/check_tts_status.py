#!/usr/bin/env python3
"""Inspect the current TTS status for a user."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
from core.database import SessionLocal, User, TTSUserSettings, WhitelistedChannel

def check_tts_status(user_id: int):
    """Print the current TTS status for a user."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            print(f'[ERROR] User {user_id} not found')
            return
        print(f'\n=== User {user_id} TTS Status ===')
        print(f'Twitch username: {user.twitch_username}')
        print(f'VK username: {user.vk_username}')
        print(f'VK channel: {user.vk_channel_name}')
        print(f'TTS Enabled (global): {user.tts_enabled}')
        tts_settings = db.query(TTSUserSettings).filter(TTSUserSettings.user_id == user_id).first()
        if tts_settings:
            print(f'\n=== TTS Settings ===')
            print(f'Engine: {tts_settings.engine}')
            print(f'Voice: {tts_settings.voice}')
            print(f'Use Local TTS: {tts_settings.use_local_tts}')
            print(f'TTS Mode: {tts_settings.tts_mode}')
        else:
            print('TTS status is unavailable for the current user')
        print(f'\n=== Whitelist Status ===')
        is_whitelisted = False
        if user.twitch_username:
            twitch_wl = db.query(WhitelistedChannel).filter(WhitelistedChannel.channel_name == user.twitch_username.lower(), WhitelistedChannel.platform == 'twitch').first()
            if twitch_wl:
                print(f" Twitch '{user.twitch_username}' IS in whitelist")
                is_whitelisted = True
            else:
                print(f"[ERROR] Twitch '{user.twitch_username}' NOT in whitelist")
        if user.vk_username:
            vk_wl = db.query(WhitelistedChannel).filter(WhitelistedChannel.channel_name == user.vk_username.lower(), WhitelistedChannel.platform == 'vk').first()
            if vk_wl:
                print(f" VK username '{user.vk_username}' IS in whitelist")
                is_whitelisted = True
            else:
                print(f"[ERROR] VK username '{user.vk_username}' NOT in whitelist")
        if user.vk_channel_name:
            vk_ch_wl = db.query(WhitelistedChannel).filter(WhitelistedChannel.channel_name == user.vk_channel_name.lower(), WhitelistedChannel.platform == 'vk').first()
            if vk_ch_wl:
                print(f" VK channel '{user.vk_channel_name}' IS in whitelist")
                is_whitelisted = True
            else:
                print(f"[ERROR] VK channel '{user.vk_channel_name}' NOT in whitelist")
        print(f'\n=== Summary ===')
        if not user.tts_enabled:
            print(f'[ERROR] TTS is DISABLED globally for this user')
            print(f'   Solution: Enable TTS in dashboard or run:')
            print(f'   UPDATE users SET tts_enabled = true WHERE id = {user_id};')
        elif not is_whitelisted and tts_settings and (tts_settings.engine == 'f5tts') and (not tts_settings.use_local_tts):
            print('[WARN] User is not in the whitelist for F5-TTS')
            print(f'   Will fallback to Google TTS')
            print(f'   To enable F5-TTS, add to whitelist:')
            if user.twitch_username:
                print(f"   INSERT INTO whitelisted_channels (channel_name, platform) VALUES ('{user.twitch_username.lower()}', 'twitch');")
            if user.vk_username:
                print(f"   INSERT INTO whitelisted_channels (channel_name, platform) VALUES ('{user.vk_username.lower()}', 'vk');")
        else:
            print(f' TTS should work (Google TTS available for all users)')
            if is_whitelisted:
                print(f' User is whitelisted (can use F5-TTS)')
    finally:
        db.close()
if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python check_tts_status.py <user_id>')
        sys.exit(1)
    user_id = int(sys.argv[1])
    check_tts_status(user_id)
