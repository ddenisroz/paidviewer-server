#!/usr/bin/env python
"""Interactive SQL console for the current project database."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text

BOT_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(BOT_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(BOT_SERVICE_ROOT))

load_dotenv(BOT_SERVICE_ROOT / '.env')

from core.database import db_session  # noqa: E402


def main() -> None:
    print('\n' + '=' * 64)
    print('DATABASE CONSOLE')
    print('=' * 64)

    with db_session() as db:
        print('Connection established.\n')
        tables = db.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
                """
            )
        ).fetchall()

        print(f'Available tables: {len(tables)}')
        for table in tables:
            print(f"- {table[0]}")

        print('\nEnter an SQL query or `exit` to quit.')
        print('Examples:')
        print('  SELECT * FROM users LIMIT 5;')
        print('  SELECT COUNT(*) FROM user_sessions;')
        print('  UPDATE users SET role = \'admin\' WHERE id = 1;')
        print()

        while True:
            try:
                query = input('SQL> ').strip()
                if query.lower() in {'exit', 'quit', 'q'}:
                    print('\nExiting console.')
                    break
                if not query:
                    continue

                result = db.execute(text(query))
                if query.lower().startswith('select'):
                    rows = result.fetchall()
                    if not rows:
                        print('(no rows)\n')
                        continue

                    headers = result.keys()
                    print('\n' + ' | '.join(headers))
                    print('-' * 80)
                    for row in rows:
                        print(' | '.join(str(value) for value in row))
                    print(f'\nRows returned: {len(rows)}\n')
                else:
                    db.commit()
                    print('Query executed successfully.\n')
            except KeyboardInterrupt:
                print('\n\nExiting console.')
                break
            except Exception as exc:
                print(f'[ERROR] {exc}\n')


if __name__ == '__main__':
    main()
