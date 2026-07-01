#!/usr/bin/env python
"""Show PostgreSQL table structure and sample data."""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text

BOT_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(BOT_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(BOT_SERVICE_ROOT))

load_dotenv(BOT_SERVICE_ROOT / '.env')

from core.database import db_session  # noqa: E402


def show_all_tables() -> None:
    print('\n' + '=' * 64)
    print('DATABASE STRUCTURE')
    print('=' * 64 + '\n')

    with db_session() as db:
        tables = db.execute(
            text(
                """
                SELECT table_name,
                       (
                           SELECT COUNT(*)
                           FROM information_schema.columns
                           WHERE table_name = t.table_name
                             AND table_schema = 'public'
                       ) AS column_count
                FROM information_schema.tables t
                WHERE table_schema = 'public'
                ORDER BY table_name
                """
            )
        ).fetchall()

        print(f'Total tables: {len(tables)}\n')
        for table_name, column_count in tables:
            try:
                row_count = db.execute(text(f'SELECT COUNT(*) FROM {table_name}')).scalar()
            except Exception:
                row_count = 'N/A'
            print(f'- {table_name}')
            print(f'  Columns: {column_count} | Rows: {row_count}')


def show_table_details(table_name: str) -> None:
    print('\n' + '=' * 64)
    print(f'TABLE: {table_name}')
    print('=' * 64 + '\n')

    with db_session() as db:
        exists = db.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = :table_name
                )
                """
            ),
            {'table_name': table_name},
        ).scalar()
        if not exists:
            print(f"[ERROR] Table '{table_name}' was not found")
            return

        columns = db.execute(
            text(
                """
                SELECT column_name,
                       data_type,
                       character_maximum_length,
                       is_nullable,
                       column_default
                FROM information_schema.columns
                WHERE table_name = :table_name
                  AND table_schema = 'public'
                ORDER BY ordinal_position
                """
            ),
            {'table_name': table_name},
        ).fetchall()

        print('Columns:\n')
        print(f"{'Name':<30} {'Type':<24} {'NULL':<8} Default")
        print('-' * 100)
        for col_name, data_type, max_length, nullable, default in columns:
            type_name = data_type if not max_length else f'{data_type}({max_length})'
            print(f"{col_name:<30} {type_name:<24} {nullable:<8} {str(default)[:32] if default else '-'}")

        indexes = db.execute(
            text(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = :table_name
                  AND schemaname = 'public'
                """
            ),
            {'table_name': table_name},
        ).fetchall()
        if indexes:
            print('\nIndexes:\n')
            for index_name, index_def in indexes:
                print(f'- {index_name}')
                print(f'  {index_def}')

        row_count = db.execute(text(f'SELECT COUNT(*) FROM {table_name}')).scalar()
        print(f'\nTotal rows: {row_count}')

        if row_count:
            rows = db.execute(text(f'SELECT * FROM {table_name} LIMIT 5')).fetchall()
            headers = db.execute(text(f'SELECT * FROM {table_name} LIMIT 1')).keys()
            print('\nFirst 5 rows:\n')
            print(' | '.join(str(header)[:18] for header in headers))
            print('-' * 100)
            for row in rows:
                print(' | '.join((str(value)[:18] if value is not None else 'NULL') for value in row))


def main() -> None:
    if len(sys.argv) > 1:
        show_table_details(sys.argv[1])
        return

    show_all_tables()
    print('\nFor a detailed table view:')
    print('  python scripts/show_db_structure.py users')
    print('  python scripts/show_db_structure.py bot_tokens')


if __name__ == '__main__':
    main()
