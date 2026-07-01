#!/usr/bin/env python3
"""Initialize default records for blocked bots."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.database import SessionLocal, BlockedBot
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_blocked_bots():
    """Ensure default blocked bot records exist if they are still missing."""
    db = SessionLocal()
    try:
        bots_to_block = ['payedviewer', 'streamelements', 'nightbot', 'streamlabs', 'moobot', 'twirapp', 'fossabot', 'streamlabs', 'wizebot', 'botrix', 'coebot', 'ankhbot', 'deepbot', 'xanbot', 'vivbot', 'ohbot', 'scorpstradamus', 'sery_bot', 'chatbot']
        added_count = 0
        skipped_count = 0
        for bot_name in bots_to_block:
            bot_name_lower = bot_name.lower()
            existing = db.query(BlockedBot).filter(BlockedBot.bot_name == bot_name_lower).first()
            if existing:
                logger.info(f"[SKIP]  Bot '{bot_name_lower}' already in blocked list")
                skipped_count += 1
                continue
            blocked_bot = BlockedBot(bot_name=bot_name_lower)
            db.add(blocked_bot)
            logger.info(f"[OK] Added bot '{bot_name_lower}' to blocked list")
            added_count += 1
        db.commit()
        print('\n' + '=' * 70)
        print('[OK] Blocked bots initialization complete!')
        print(f'   Added: {added_count}')
        print(f'   Skipped (already exists): {skipped_count}')
        print(f'   Total blocked bots: {added_count + skipped_count}')
        print('=' * 70)
        all_blocked = db.query(BlockedBot).order_by(BlockedBot.bot_name).all()
        print('\n[LIST] Current blocked bots list:')
        for bot in all_blocked:
            marker = '[BLOCKED]' if bot.bot_name == 'payedviewer' else '[BOT]'
            print(f'   {marker} {bot.bot_name}')
        print()
    except Exception as e:
        logger.error(f'[ERROR] Error initializing blocked bots: {e}')
        db.rollback()
        raise
    finally:
        db.close()
if __name__ == '__main__':
    print('[BOT] Initializing blocked bots list...')
    print('   These bots will NOT be voiced by TTS\n')
    init_blocked_bots()
    print('[OK] Done!')
