"""add_performance_indexes

Revision ID: 4cf879f958cd
Revises: 7aa272ec1bfc
Create Date: 2025-11-03 10:46:46.709292

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '4cf879f958cd'
down_revision: Union[str, None] = '7aa272ec1bfc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Добавляем составные индексы для оптимизации частых запросов"""

    # Проверяем тип БД через connection
    connection = op.get_bind()

    # ChatMessage индексы для частых запросов
    # Составной индекс для фильтрации по каналу и платформе с сортировкой по времени
    # Используется в get_chat_history, get_stream_history
    # Для PostgreSQL можно использовать DESC в индексе, но проще сделать обычный индекс
    # БД сама оптимизирует ORDER BY с индексом
    op.create_index(
        'idx_chat_channel_platform_timestamp',
        'chat_messages',
        ['channel_name', 'platform', 'timestamp'],
        unique=False
    )

    # Составной индекс для получения истории пользователя по каналу
    # Используется в additional_api.get_chat_history
    op.create_index(
        'idx_chat_user_channel_timestamp',
        'chat_messages',
        ['user_id', 'channel_name', 'timestamp'],
        unique=False
    )

    # Индекс для фильтрации по is_deleted (часто используется)
    op.create_index(
        'idx_chat_is_deleted',
        'chat_messages',
        ['is_deleted'],
        unique=False
    )

    # WhitelistedChannel - unique constraint уже создает индекс, пропускаем

    # UserSettings - индекс для частых запросов по user_id
    # Проверяем существование перед созданием (может уже быть index=True на колонке)
    try:
        inspector = inspect(connection)
        existing_user_settings_indexes = [idx['name'] for idx in inspector.get_indexes('user_settings')]
        if 'idx_user_settings_user_id' not in existing_user_settings_indexes:
            # Проверяем есть ли индекс на user_id вообще
            user_id_has_index = any(
                'user_id' in idx.get('column_names', [])
                for idx in inspector.get_indexes('user_settings')
            )
            if not user_id_has_index:
                op.create_index(
                    'idx_user_settings_user_id',
                    'user_settings',
                    ['user_id'],
                    unique=False
                )
    except Exception:
        # Если inspector не работает, просто пытаемся создать
        try:
            op.create_index(
                'idx_user_settings_user_id',
                'user_settings',
                ['user_id'],
                unique=False
            )
        except Exception:
            pass  # Уже существует

    # TTSUserSettings - индексы для запросов по user_id и session_id
    try:
        existing_tts_indexes = [idx['name'] for idx in inspector.get_indexes('tts_user_settings')]

        # Проверяем есть ли индексы на этих полях
        user_id_has_index = any(
            'user_id' in idx.get('column_names', [])
            for idx in inspector.get_indexes('tts_user_settings')
        )
        if not user_id_has_index and 'idx_tts_settings_user_id' not in existing_tts_indexes:
            op.create_index(
                'idx_tts_settings_user_id',
                'tts_user_settings',
                ['user_id'],
                unique=False
            )

        session_id_has_index = any(
            'session_id' in idx.get('column_names', [])
            for idx in inspector.get_indexes('tts_user_settings')
        )
        if not session_id_has_index and 'idx_tts_settings_session_id' not in existing_tts_indexes:
            op.create_index(
                'idx_tts_settings_session_id',
                'tts_user_settings',
                ['session_id'],
                unique=False
            )
    except Exception:
        # Если inspector не работает, просто пытаемся создать
        try:
            op.create_index('idx_tts_settings_user_id', 'tts_user_settings', ['user_id'], unique=False)
        except Exception:
            pass
        try:
            op.create_index('idx_tts_settings_session_id', 'tts_user_settings', ['session_id'], unique=False)
        except Exception:
            pass


def downgrade() -> None:
    """Удаляем добавленные индексы"""

    # Удаляем индексы с обработкой ошибок (на случай если их нет)
    try:
        op.drop_index('idx_chat_channel_platform_timestamp', table_name='chat_messages')
    except Exception:
        pass

    try:
        op.drop_index('idx_chat_user_channel_timestamp', table_name='chat_messages')
    except Exception:
        pass

    try:
        op.drop_index('idx_chat_is_deleted', table_name='chat_messages')
    except Exception:
        pass

    try:
        op.drop_index('idx_whitelist_channel_platform', table_name='whitelisted_channels')
    except Exception:
        pass  # Индекс может быть частью unique constraint

    try:
        op.drop_index('idx_user_settings_user_id', table_name='user_settings')
    except Exception:
        pass

    try:
        op.drop_index('idx_tts_settings_user_id', table_name='tts_user_settings')
    except Exception:
        pass

    try:
        op.drop_index('idx_tts_settings_session_id', table_name='tts_user_settings')
    except Exception:
        pass
