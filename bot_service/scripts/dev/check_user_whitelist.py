#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script for inspecting a user's whitelist status.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import User, WhitelistedChannel, get_db
from utils.whitelist_cache import is_user_whitelisted_cached, invalidate_whitelist_cache

def check_user_whitelist(user_id: int):
    """Check a user's whitelist status."""
    db = next(get_db())
    try:
        # Load the user record.
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            print(f"[ERROR] User with ID {user_id} not found")
            return
        
        print(f"\n=== User ID {user_id} Information ===")
        print(f"Twitch username: {user.twitch_username or 'not set'}")
        print(f"VK username: {user.vk_username or 'not set'}")
        print(f"VK channel name: {user.vk_channel_name or 'not set'}")
        print(f"is_admin: {user.is_admin}")
        print(f"is_active: {user.is_active}")
        
        # Check whitelist status directly in the database.
        print(f"\n=== Whitelist Check in DB ===")
        
        twitch_in_whitelist = False
        vk_in_whitelist = False
        
        if user.twitch_username:
            twitch_whitelisted = db.query(WhitelistedChannel).filter(
                WhitelistedChannel.channel_name == user.twitch_username.lower(),
                WhitelistedChannel.platform == 'twitch'
            ).first()
            twitch_in_whitelist = bool(twitch_whitelisted)
            status = "IN whitelist" if twitch_in_whitelist else "NOT in whitelist"
            print(f"Twitch ({user.twitch_username.lower()}): {status}")
            if twitch_whitelisted:
                print(f"  Record ID: {twitch_whitelisted.id}, created: {twitch_whitelisted.created_at}")
        
        if user.vk_username:
            vk_whitelisted = db.query(WhitelistedChannel).filter(
                WhitelistedChannel.channel_name == user.vk_username.lower(),
                WhitelistedChannel.platform == 'vk'
            ).first()
            vk_in_whitelist = bool(vk_whitelisted)
            status = "IN whitelist" if vk_in_whitelist else "NOT in whitelist"
            print(f"VK ({user.vk_username.lower()}): {status}")
            if vk_whitelisted:
                print(f"  Record ID: {vk_whitelisted.id}, created: {vk_whitelisted.created_at}")
        
        # Check the cached whitelist resolver.
        print(f"\n=== Check via cached function ===")
        is_whitelisted = is_user_whitelisted_cached(user, db)
        status = "IN whitelist" if is_whitelisted else "NOT in whitelist"
        print(f"Result: {status}")
        
        # Print all whitelist rows for debugging.
        print(f"\n=== All whitelist entries ===")
        all_whitelist = db.query(WhitelistedChannel).all()
        if all_whitelist:
            for wl in all_whitelist:
                print(f"  - {wl.channel_name} ({wl.platform})")
        else:
            print("  Whitelist is empty")
        
        # Print the final status summary.
        print(f"\n{'='*60}")
        if is_whitelisted:
            print(f"[OK] User ID {user_id} IS IN WHITELIST")
        else:
            print(f"[FAIL] User ID {user_id} IS NOT IN WHITELIST")
            if user.twitch_username or user.vk_username:
                print(f"\nTo add to whitelist:")
                if user.twitch_username:
                    print(f"  POST /api/admin/whitelist/add")
                    print(f"  Body: {{'username': '{user.twitch_username}', 'platform': 'twitch'}}")
                if user.vk_username:
                    print(f"  POST /api/admin/whitelist/add")
                    print(f"  Body: {{'username': '{user.vk_username}', 'platform': 'vk'}}")
        print(f"{'='*60}\n")
        
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    user_id = 1
    if len(sys.argv) > 1:
        try:
            user_id = int(sys.argv[1])
        except ValueError:
            print(f"[ERROR] Invalid user ID: {sys.argv[1]}")
            sys.exit(1)
    
    check_user_whitelist(user_id)
