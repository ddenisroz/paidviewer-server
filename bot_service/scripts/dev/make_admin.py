#!/usr/bin/env python3
"""
Make a user an administrator.

Usage:
    python scripts/make_admin.py <user_id>
    python scripts/make_admin.py --username <twitch_username>
"""

import sys
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path
BOT_SERVICE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(BOT_SERVICE_ROOT))

# Load .env
env_path = BOT_SERVICE_ROOT / '.env'
load_dotenv(dotenv_path=env_path, override=True)

from core.database import SessionLocal, User  # noqa: E402


def make_admin(user_id=None, username=None):
    """Make a user an administrator."""
    db = SessionLocal()
    try:
        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
        elif username:
            user = db.query(User).filter(
                (User.twitch_username == username.lower()) |
                (User.vk_username == username.lower())
            ).first()
        else:
            print("[ERROR] Specify user_id or username")
            return False

        if not user:
            print("[ERROR] User not found")
            return False

        if user.role == 'admin' or user.is_admin:
            print("[OK] User is already an admin:")
            print(f"   ID: {user.id}")
            print(f"   Twitch: {user.twitch_username or 'not configured'}")
            print(f"   VK: {user.vk_username or 'not configured'}")
            return True

        # Grant admin role.
        user.role = 'admin'
        user.is_admin = True
        db.commit()

        print("[OK] User is now an administrator:")
        print(f"   ID: {user.id}")
        print(f"   Twitch: {user.twitch_username or 'not configured'}")
        print(f"   VK: {user.vk_username or 'not configured'}")
        print(f"   Role: {user.role}")
        print(f"   Admin: {user.role == 'admin' or user.is_admin}")
        print("\nNext:")
        print("1. Open http://localhost:8000/auth/twitch/bot/login")
        print("2. Authorize the bot via OAuth2")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to update user role: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def list_users():
    """Show all users."""
    db = SessionLocal()
    try:
        users = db.query(User).all()

        if not users:
            print("[ERROR] No users found")
            print("\nAuthorize first via:")
            print("- http://localhost:8000/auth/twitch/login")
            print("- http://localhost:8000/auth/vk/login")
            return

        print(f"Users found: {len(users)}\n")

        for user in users:
            print(f"ID: {user.id}")
            print(f"  Twitch: {user.twitch_username or 'not configured'}")
            print(f"  VK: {user.vk_username or 'not configured'}")
            print(f"  Admin: {'yes' if (user.role == 'admin' or user.is_admin) else 'no'}")
            print()

        print("To make a user an administrator:")
        print(f"  python scripts/make_admin.py {users[0].id}")
        print(f"  python scripts/make_admin.py --username {users[0].twitch_username or users[0].vk_username}")
        
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) == 1 or sys.argv[1] in ['--list', '-l']:
        list_users()
    elif len(sys.argv) == 2:
        try:
            user_id = int(sys.argv[1])
            make_admin(user_id=user_id)
        except ValueError:
            print("[ERROR] Invalid user_id format")
            print("Usage: python scripts/make_admin.py <user_id>")
    elif len(sys.argv) == 3 and sys.argv[1] in ['--username', '-u']:
        make_admin(username=sys.argv[2])
    else:
        print("Usage:")
        print("  python scripts/make_admin.py                    # Show all users")
        print("  python scripts/make_admin.py <user_id>          # Make user admin by ID")
        print("  python scripts/make_admin.py --username <name>  # Make user admin by username")
