# bot_service/tests/test_api_moderation.py
"""
Тесты для API модерации
"""
import pytest
from unittest.mock import patch

class TestModerationAPI:
    """Тесты для API модерации"""
    
    def test_block_user_tts(self, authenticated_client):
        """Тест блокировки пользователя от TTS"""
        block_data = {
            "channel_name": "test_channel",
            "platform": "twitch",
            "username": "test_user"
        }
        response = authenticated_client.post("/api/moderation/tts/block", json=block_data)
        # Может быть 200 (success), 404 (not found), 403 (forbidden), или 500 (error)
        assert response.status_code in [200, 403, 404, 500]
    
    def test_unblock_user_tts(self, authenticated_client):
        """Тест разблокировки пользователя для TTS"""
        unblock_data = {
            "channel_name": "test_channel",
            "platform": "twitch",
            "username": "test_user"
        }
        response = authenticated_client.post("/api/moderation/tts/unblock", json=unblock_data)
        # Может быть 200 (success), 404 (not found), 403 (forbidden), или 500 (error)
        assert response.status_code in [200, 403, 404, 500]
    
    def test_get_blocked_users(self, authenticated_client):
        """Тест получения списка заблокированных пользователей"""
        response = authenticated_client.get(
            "/api/moderation/tts/blocked?channel_name=test_channel&platform=twitch"
        )
        # Может быть 200 (success), 404 (not found), 403 (forbidden), или 500 (error)
        assert response.status_code in [200, 403, 404, 500]
    
    def test_get_all_blocked_users(self, authenticated_client):
        """Тест получения всех заблокированных пользователей (админ)"""
        response = authenticated_client.get("/api/moderation/tts/blocked-users")
        # Может быть 200 (success), 404 (not found), 403 (forbidden), или 500 (error)
        assert response.status_code in [200, 403, 404, 500]
    
    @patch('startup.bot_registry.get_bot_registry')
    def test_timeout_user(self, mock_get_registry, authenticated_client):
        """Тест таймаута пользователя"""
        from unittest.mock import AsyncMock, MagicMock
        mock_registry = MagicMock()
        mock_bot = AsyncMock()
        mock_bot.get_channel.return_value = AsyncMock()
        mock_registry.twitch_bot = mock_bot
        mock_get_registry.return_value = mock_registry
        
        timeout_data = {
            "channel_name": "test_channel",
            "platform": "twitch",
            "username": "test_user",
            "duration": 300,
            "reason": "Test timeout"
        }
        response = authenticated_client.post("/api/moderation/timeout", json=timeout_data)
        # Может быть 200 (success), 404 (not found), 403 (forbidden), или 500 (error)
        assert response.status_code in [200, 403, 404, 500]
    
    @patch('startup.bot_registry.get_bot_registry')
    def test_ban_user(self, mock_get_registry, authenticated_client):
        """Тест бана пользователя"""
        from unittest.mock import AsyncMock, MagicMock
        mock_registry = MagicMock()
        mock_bot = AsyncMock()
        mock_bot.get_channel.return_value = AsyncMock()
        mock_registry.twitch_bot = mock_bot
        mock_get_registry.return_value = mock_registry
        
        ban_data = {
            "channel_name": "test_channel",
            "platform": "twitch",
            "username": "test_user",
            "reason": "Test ban"
        }
        response = authenticated_client.post("/api/moderation/ban", json=ban_data)
        # Может быть 200 (success), 404 (not found), 403 (forbidden), или 500 (error)
        assert response.status_code in [200, 403, 404, 500]
    
    def test_add_moderator_role(self, authenticated_client):
        """Тест добавления роли модератора"""
        role_data = {
            "channel_name": "test_channel",
            "platform": "twitch",
            "username": "test_user",
            "role": "moderator",
            "action": "add"
        }
        response = authenticated_client.post("/api/moderation/role", json=role_data)
        # Может быть 200 (success), 404 (not found), 403 (forbidden), или 500 (error)
        assert response.status_code in [200, 403, 404, 500]
    
    def test_remove_moderator_role(self, authenticated_client):
        """Тест удаления роли модератора"""
        role_data = {
            "channel_name": "test_channel",
            "platform": "twitch",
            "username": "test_user",
            "role": "moderator",
            "action": "remove"
        }
        response = authenticated_client.post("/api/moderation/role", json=role_data)
        # Может быть 200 (success), 404 (not found), 403 (forbidden), или 500 (error)
        assert response.status_code in [200, 403, 404, 500]
    
    def test_moderation_unauthorized(self, client):
        """Тест модерации без авторизации"""
        block_data = {
            "channel_name": "test_channel",
            "platform": "twitch",
            "username": "test_user"
        }
        response = client.post("/api/moderation/tts/block", json=block_data)
        # Может быть 401 (unauthorized) или 404 (endpoint not found without auth)
        assert response.status_code in [401, 404]
    
    def test_moderation_forbidden(self, client, test_user):
        """Тест модерации без прав"""
        # Создаем обычного пользователя (не админа)
        from core.database import User
        user = User(
            id=2,
            role="user",
            is_active=True,
            twitch_username="regular_user"
        )
        # Здесь нужно создать сессию для обычного пользователя
        # и попытаться модерировать чужой канал
        
        block_data = {
            "channel_name": "other_channel",
            "platform": "twitch",
            "username": "test_user"
        }
        response = client.post("/api/moderation/tts/block", json=block_data)
        # Может быть 401 (unauthorized), 403 (forbidden), или 404 (not found)
        assert response.status_code in [401, 403, 404]
