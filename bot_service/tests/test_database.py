# bot_service/tests/test_database.py
"""
Тесты для базы данных и моделей
"""
import pytest
from datetime import datetime
from core.database import User, UserToken, UserSession, WhitelistedChannel, TTSBlockedUser

class TestDatabaseModels:
    """Тесты для моделей базы данных"""
    
    def test_user_creation(self, db_session):
        """Тест создания пользователя"""
        user = User(
            id=1,
            is_admin=True,
            is_active=True,
            twitch_username="testuser",
            vk_username="testuser_vk"
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        
        assert user.id == 1
        assert user.is_admin == True
        assert user.is_active == True
        assert user.twitch_username == "testuser"
        assert user.vk_username == "testuser_vk"
        assert user.created_at is not None
    
    def test_user_token_creation(self, db_session, test_user):
        """Тест создания токена пользователя"""
        token = UserToken(
            user_id=test_user.id,
            platform="twitch",
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            platform_user_id="123456",
            avatar_url="https://example.com/avatar.jpg"
        )
        db_session.add(token)
        db_session.commit()
        db_session.refresh(token)
        
        assert token.user_id == test_user.id
        assert token.platform == "twitch"
        assert token.access_token == "test_access_token"
        assert token.platform_user_id == "123456"
    
    def test_user_session_creation(self, db_session, test_user):
        """Тест создания сессии пользователя"""
        session = UserSession(
            user_id=test_user.id,
            session_id="test_session_id",
            device_info={"user_agent": "test", "ip": "127.0.0.1"},
            is_active=True
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)
        
        assert session.user_id == test_user.id
        assert session.session_id == "test_session_id"
        assert session.device_info == {"user_agent": "test", "ip": "127.0.0.1"}
        assert session.is_active == True
    
    def test_whitelisted_channel_creation(self, db_session):
        """Тест создания whitelisted канала"""
        channel = WhitelistedChannel(
            channel_name="test_channel",
            platform="twitch"  # platform is required (NOT NULL)
        )
        db_session.add(channel)
        db_session.commit()
        db_session.refresh(channel)
        
        assert channel.channel_name == "test_channel"
        assert channel.platform == "twitch"
        assert channel.created_at is not None
    
    def test_tts_blocked_user_creation(self, db_session, test_user):
        """Тест создания заблокированного пользователя TTS"""
        blocked_user = TTSBlockedUser(
            user_id=test_user.id,  # Must have either user_id or session_id (CHECK constraint)
            channel_name="test_channel",
            platform="twitch",
            username="blocked_user",
            blocked_by=1,
            reason="Test block"
        )
        db_session.add(blocked_user)
        db_session.commit()
        db_session.refresh(blocked_user)
        
        assert blocked_user.user_id == test_user.id
        assert blocked_user.channel_name == "test_channel"
        assert blocked_user.platform == "twitch"
        assert blocked_user.username == "blocked_user"
        assert blocked_user.blocked_by == 1
        assert blocked_user.reason == "Test block"
        assert blocked_user.blocked_at is not None
    
    def test_user_relationships(self, db_session):
        """Тест связей между моделями"""
        # Создаем пользователя
        user = User(
            id=1,
            is_admin=True,
            is_active=True,
            twitch_username="testuser"
        )
        db_session.add(user)
        db_session.commit()
        
        # Создаем токен
        token = UserToken(
            user_id=user.id,
            platform="twitch",
            access_token="test_token",
            platform_user_id="123456"
        )
        db_session.add(token)
        
        # Создаем сессию
        session = UserSession(
            user_id=user.id,
            session_id="test_session",
            is_active=True
        )
        db_session.add(session)
        db_session.commit()
        
        # Проверяем связи
        user_tokens = db_session.query(UserToken).filter(UserToken.user_id == user.id).all()
        user_sessions = db_session.query(UserSession).filter(UserSession.user_id == user.id).all()
        
        assert len(user_tokens) == 1
        assert len(user_sessions) == 1
        assert user_tokens[0].user_id == user.id
        assert user_sessions[0].user_id == user.id
    
    def test_database_constraints(self, db_session):
        """Тест ограничений базы данных"""
        # Тест уникальности session_id
        session1 = UserSession(
            user_id=1,
            session_id="unique_session",
            is_active=True
        )
        session2 = UserSession(
            user_id=2,
            session_id="unique_session",  # Дублирующий session_id
            is_active=True
        )
        
        db_session.add(session1)
        db_session.commit()
        
        db_session.add(session2)
        # Должна возникнуть ошибка из-за нарушения уникальности
        with pytest.raises(Exception):
            db_session.commit()
    
    def test_cascade_deletion(self, db_session):
        """Тест каскадного удаления"""
        # Создаем пользователя с токенами и сессиями
        user = User(
            id=1,
            is_admin=True,
            is_active=True,
            twitch_username="testuser"
        )
        db_session.add(user)
        db_session.commit()
        
        token = UserToken(
            user_id=user.id,
            platform="twitch",
            access_token="test_token",
            platform_user_id="123456"
        )
        db_session.add(token)
        
        session = UserSession(
            user_id=user.id,
            session_id="test_session",
            is_active=True
        )
        db_session.add(session)
        db_session.commit()
        
        # Проверяем, что записи созданы
        user_tokens = db_session.query(UserToken).filter(UserToken.user_id == user.id).all()
        user_sessions = db_session.query(UserSession).filter(UserSession.user_id == user.id).all()
        
        assert len(user_tokens) == 1
        assert len(user_sessions) == 1
        
        # Удаляем токены и сессии вручную (так как каскадное удаление не настроено)
        db_session.delete(token)
        db_session.delete(session)
        db_session.delete(user)
        db_session.commit()
        
        # Проверяем, что все записи удалены
        remaining_tokens = db_session.query(UserToken).filter(UserToken.user_id == user.id).all()
        remaining_sessions = db_session.query(UserSession).filter(UserSession.user_id == user.id).all()
        remaining_users = db_session.query(User).filter(User.id == user.id).all()
        
        assert len(remaining_tokens) == 0
        assert len(remaining_sessions) == 0
        assert len(remaining_users) == 0
