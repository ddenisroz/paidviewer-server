#!/usr/bin/env python3
"""
Check whether an admin user exists in the system.
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


def check_admin():
    """Check whether an admin user exists."""
    db = SessionLocal()
    try:
        # Find admin user
        admin = db.query(User).filter((User.role == 'admin') | (User.is_admin.is_(True))).first()
        
        if admin:
            print(" Admin user found:")
            print(f"   ID: {admin.id}")
            print(f"   Twitch: {admin.twitch_username or 'not configured'}")
            print(f"   VK: {admin.vk_username or 'not configured'}")
            print(f"   Role: {admin.role}")
            print(f"   Admin: {admin.role == 'admin' or admin.is_admin}")
            return True
        else:
            print("[ERROR] Admin user was not found")
            print("\nAdmin rights are required to authorize a bot via OAuth.")
            print("\nOptions:")
            print("1. Sign in via OAuth (Twitch or VK)")
            print("2. Promote your user to admin:")
            print("   UPDATE users SET role = 'admin', is_admin = true WHERE id = YOUR_USER_ID;")
            return False
            
    finally:
        db.close()


if __name__ == "__main__":
    check_admin()
