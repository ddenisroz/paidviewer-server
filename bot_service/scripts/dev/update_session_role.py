#!/usr/bin/env python3
"""Update roles in active sessions after changing is_admin."""

import sys
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path
BOT_SERVICE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(BOT_SERVICE_ROOT))

# Load .env
env_path = BOT_SERVICE_ROOT / '.env'
load_dotenv(dotenv_path=env_path, override=True)

from core.database import SessionLocal, User, UserSession  # noqa: E402
from core.session_manager import session_manager  # noqa: E402


def update_sessions():
    """Update roles in active sessions."""
    db = SessionLocal()
    try:
        # Find all admins.
        admins = db.query(User).filter(User.is_admin).all()

        if not admins:
            print("[ERROR] No admins found")
            return

        print(f"Admins found: {len(admins)}\n")
        
        updated_count = 0

        for admin in admins:
            print(f"Updating sessions for: {admin.twitch_username or admin.vk_username} (ID: {admin.id})")

            # Find active user sessions.
            sessions = db.query(UserSession).filter(
                UserSession.user_id == admin.id,
                UserSession.is_active
            ).all()

            if not sessions:
                print("  [WARN] No active sessions found")
                continue

            print(f"  Active sessions found: {len(sessions)}")

            for session in sessions:
                # Update the role in session_manager.
                session_data = session_manager.get_session(session.session_id)

                if session_data:
                    session_data['is_admin'] = True
                    session_data['role'] = 'admin'
                    session_manager.update_session(session.session_id, session_data)
                    print(f"   Session {session.session_id[:8]}... updated")
                    updated_count += 1
                else:
                    print(f"  [WARN] Session {session.session_id[:8]}... not found in memory")
            
            print()
        
        print(f"\nSessions updated: {updated_count}")
        print("\nNext:")
        print("1. Refresh the page in the browser (F5)")
        print("2. Open http://localhost:8000/auth/twitch/bot/login")
        
    finally:
        db.close()


if __name__ == "__main__":
    update_sessions()
