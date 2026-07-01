"""add_production_indexes

Revision ID: e1bfe023c304
Revises: 
Create Date: 2025-10-25

Production-ready indexes для оптимизации запросов
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e1bfe023c304'
down_revision = None  # Будет заполнено автоматически
depends_on = None


def upgrade():
    """
    Создание индексов для production оптимизации
    
    Индексы на часто используемых полях для ускорения запросов:
    - users: twitch_username, vk_username, created_at
    - user_tokens: user_id+platform, platform_user_id
    - user_sessions: user_id+is_active, session_id
    - bot_commands: user_id+is_enabled, command_name
    - chat_messages: user_id+platform, created_at
    - filtered_words: user_id+word
    """
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Проверяем какие таблицы существуют
    tables = inspector.get_table_names()

    # === USERS TABLE ===
    if 'users' in tables:
        # Индекс на twitch_username (уже unique, но добавим для JOIN оптимизации)
        try:
            op.create_index('idx_users_twitch_username', 'users', ['twitch_username'])
        except Exception:
            pass  # Может уже существовать

        # Индекс на vk_username
        try:
            op.create_index('idx_users_vk_username', 'users', ['vk_username'])
        except Exception:
            pass

        # Индекс на created_at для сортировки
        try:
            op.create_index('idx_users_created_at', 'users', ['created_at'])
        except Exception:
            pass

        # Индекс на is_active для фильтрации
        try:
            op.create_index('idx_users_is_active', 'users', ['is_active'])
        except Exception:
            pass

    # === USER_TOKENS TABLE ===
    if 'user_tokens' in tables:
        # Композитный индекс user_id + platform (частый запрос)
        try:
            op.create_index('idx_user_tokens_user_platform', 'user_tokens', ['user_id', 'platform'])
        except Exception:
            pass

        # Индекс на platform_user_id для поиска по внешнему ID
        try:
            op.create_index('idx_user_tokens_platform_user_id', 'user_tokens', ['platform_user_id'])
        except Exception:
            pass

        # Индекс на is_active для фильтрации активных токенов
        try:
            op.create_index('idx_user_tokens_is_active', 'user_tokens', ['is_active'])
        except Exception:
            pass

    # === USER_SESSIONS TABLE ===
    if 'user_sessions' in tables:
        # Композитный индекс user_id + is_active
        try:
            op.create_index('idx_user_sessions_user_active', 'user_sessions', ['user_id', 'is_active'])
        except Exception:
            pass

        # Индекс на session_id (частый поиск)
        try:
            op.create_index('idx_user_sessions_session_id', 'user_sessions', ['session_id'])
        except Exception:
            pass

    # === BOT_COMMANDS TABLE ===
    if 'bot_commands' in tables:
        # Композитный индекс user_id + is_enabled
        try:
            op.create_index('idx_bot_commands_user_enabled', 'bot_commands', ['user_id', 'is_enabled'])
        except Exception:
            pass

        # Индекс на command_name для поиска команд
        try:
            op.create_index('idx_bot_commands_command_name', 'bot_commands', ['command_name'])
        except Exception:
            pass

    # === CHAT_MESSAGES TABLE ===
    if 'chat_messages' in tables:
        # Композитный индекс user_id + platform
        try:
            op.create_index('idx_chat_messages_user_platform', 'chat_messages', ['user_id', 'platform'])
        except Exception:
            pass

        # Индекс на created_at для сортировки по времени
        try:
            op.create_index('idx_chat_messages_created_at', 'chat_messages', ['created_at'])
        except Exception:
            pass

        # Индекс на channel_name для фильтрации по каналу
        try:
            op.create_index('idx_chat_messages_channel', 'chat_messages', ['channel_name'])
        except Exception:
            pass

    # === FILTERED_WORDS TABLE ===
    if 'filtered_words' in tables:
        # Композитный индекс user_id + word
        try:
            op.create_index('idx_filtered_words_user_word', 'filtered_words', ['user_id', 'word'])
        except Exception:
            pass

    # === STREAM_DATA TABLE (если существует) ===
    if 'stream_data' in tables:
        # Композитный индекс user_id + platform
        try:
            op.create_index('idx_stream_data_user_platform', 'stream_data', ['user_id', 'platform'])
        except Exception:
            pass

        # Индекс на is_live для поиска активных стримов
        try:
            op.create_index('idx_stream_data_is_live', 'stream_data', ['is_live'])
        except Exception:
            pass


def downgrade():
    """Удаление индексов при откате"""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    # Удаляем все созданные индексы
    if 'users' in tables:
        try:
            op.drop_index('idx_users_twitch_username', 'users')
        except Exception:
            pass
        try:
            op.drop_index('idx_users_vk_username', 'users')
        except Exception:
            pass
        try:
            op.drop_index('idx_users_created_at', 'users')
        except Exception:
            pass
        try:
            op.drop_index('idx_users_is_active', 'users')
        except Exception:
            pass

    if 'user_tokens' in tables:
        try:
            op.drop_index('idx_user_tokens_user_platform', 'user_tokens')
        except Exception:
            pass
        try:
            op.drop_index('idx_user_tokens_platform_user_id', 'user_tokens')
        except Exception:
            pass
        try:
            op.drop_index('idx_user_tokens_is_active', 'user_tokens')
        except Exception:
            pass

    if 'user_sessions' in tables:
        try:
            op.drop_index('idx_user_sessions_user_active', 'user_sessions')
        except Exception:
            pass
        try:
            op.drop_index('idx_user_sessions_session_id', 'user_sessions')
        except Exception:
            pass

    if 'bot_commands' in tables:
        try:
            op.drop_index('idx_bot_commands_user_enabled', 'bot_commands')
        except Exception:
            pass
        try:
            op.drop_index('idx_bot_commands_command_name', 'bot_commands')
        except Exception:
            pass

    if 'chat_messages' in tables:
        try:
            op.drop_index('idx_chat_messages_user_platform', 'chat_messages')
        except Exception:
            pass
        try:
            op.drop_index('idx_chat_messages_created_at', 'chat_messages')
        except Exception:
            pass
        try:
            op.drop_index('idx_chat_messages_channel', 'chat_messages')
        except Exception:
            pass

    if 'filtered_words' in tables:
        try:
            op.drop_index('idx_filtered_words_user_word', 'filtered_words')
        except Exception:
            pass

    if 'stream_data' in tables:
        try:
            op.drop_index('idx_stream_data_user_platform', 'stream_data')
        except Exception:
            pass
        try:
            op.drop_index('idx_stream_data_is_live', 'stream_data')
        except Exception:
            pass
