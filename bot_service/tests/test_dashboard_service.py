# bot_service/tests/test_dashboard_service.py
"""
Tests for DashboardService.
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from services.dashboard_service import DashboardService
from models.user import User
from models.tts import TTSUserSettings, AudioSettings
from core.database import UserToken, ChatMessage

class TestDashboardService:
    @pytest.fixture
    def mock_db(self):
        return Mock()

    @pytest.fixture
    def dashboard_service(self, mock_db):
        with patch('services.dashboard_service.UserRepository') as mock_user_repo, \
             patch('services.dashboard_service.UserTokenRepository') as mock_token_repo, \
             patch('services.dashboard_service.TTSSettingsRepository') as mock_tts_repo, \
             patch('services.dashboard_service.AudioSettingsRepository') as mock_audio_repo, \
             patch('services.dashboard_service.ChatMessageRepository') as mock_chat_repo:
            
            service = DashboardService(mock_db)
            service.user_repo = mock_user_repo.return_value
            service.token_repo = mock_token_repo.return_value
            service.tts_repo = mock_tts_repo.return_value
            service.audio_repo = mock_audio_repo.return_value
            service.chat_repo = mock_chat_repo.return_value
            return service

    @pytest.mark.asyncio
    async def test_get_dashboard_init_data_no_user(self, dashboard_service):
        """Test with no current user returns default empty response."""
        result = await dashboard_service.get_dashboard_init_data(None)
        
        assert result["success"] == True
        assert result["user"] is None
        assert result["integrations"] == {}

    @pytest.mark.asyncio
    async def test_get_dashboard_init_data_success(self, dashboard_service):
        """Test successful data aggregation."""
        user_id = 1
        current_user = {"id": user_id}
        
        # Mock User
        mock_user = Mock(spec=User)
        mock_user.id = user_id
        mock_user.twitch_username = "tester"
        mock_user.vk_username = None
        mock_user.vk_channel_name = None
        mock_user.is_admin = False
        mock_user.created_at = datetime(2023, 1, 1)
        dashboard_service.user_repo.get_by_id.return_value = mock_user

        # Mock Tokens (Integrations)
        mock_token = Mock(spec=UserToken)
        mock_token.platform = "twitch"
        mock_token.access_token = "valid_token"
        mock_token.platform_user_id = "12345"
        mock_token.avatar_url = "http://avatar.url"
        dashboard_service.token_repo.get_all_by_user.return_value = [mock_token]

        # Mock TTS Settings
        mock_tts = Mock(spec=TTSUserSettings)
        mock_tts.enabled = True
        mock_tts.enabled_platforms = ["twitch"]
        mock_tts.global_enabled = True
        mock_tts.voice_id = "test_voice"
        dashboard_service.tts_repo.get_by_user_id.return_value = mock_tts

        mock_audio = Mock(spec=AudioSettings)
        mock_audio.volume = 75
        dashboard_service.audio_repo.get_by_user_id.return_value = mock_audio

        # Mock Chat History
        mock_msg = Mock(spec=ChatMessage)
        mock_msg.id = 100
        mock_msg.message = "Hello"
        mock_msg.platform = "twitch"
        mock_msg.timestamp = datetime(2023, 1, 1, 12, 0, 0)
        mock_msg.channel_name = "tester"
        # Mock attributes that might be missing dynamically
        mock_msg.author_username = "viewer"
        mock_msg.role = "user"
        mock_msg.badges = None
        
        dashboard_service.chat_repo.get_by_channel.return_value = [mock_msg]

        # Patch validate_platform_token
        with patch('services.dashboard_service.validate_platform_token', new_callable=AsyncMock) as mock_val:
            mock_val.return_value = True
            
            result = await dashboard_service.get_dashboard_init_data(current_user)

        assert result["success"] == True
        assert result["user"]["id"] == user_id
        assert result["user"]["twitch_username"] == "tester"
        
        # Verify integrations
        assert "twitch" in result["integrations"]
        assert result["integrations"]["twitch"]["connected"] == True
        assert result["integrations"]["twitch"]["username"] == "tester"

        # Verify TTS
        assert result["tts"]["enabled"] == True
        assert result["tts"]["volume"] == 75

        # Verify Chat (reversed order check)
        assert len(result["chat_history"]) == 1
        assert result["chat_history"][0]["id"] == 100

    @pytest.mark.asyncio
    async def test_get_dashboard_init_data_user_not_found_in_db(self, dashboard_service):
        """Test when user exists in token but not in DB (edge case)."""
        dashboard_service.user_repo.get_by_id.return_value = None
        
        result = await dashboard_service.get_dashboard_init_data({"id": 999})
        
        assert result["success"] == True
        assert result["user"] is None
