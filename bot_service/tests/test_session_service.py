# bot_service/tests/test_session_service.py
"""
Tests for SessionService.
"""
import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from services.session_service import SessionService
from models.user import UserToken

class TestSessionService:
    @pytest.fixture
    def mock_db(self):
        return Mock()

    @pytest.fixture
    def mock_token_repo(self):
        return Mock()

    @pytest.fixture
    def mock_connection_manager(self):
        return Mock()

    @pytest.fixture
    def session_service(self, mock_db, mock_token_repo, mock_connection_manager):
        # Patch dependencies inside the service initialization
        with patch('services.session_service.UserTokenRepository') as repo_cls, \
             patch('services.session_service.get_connection_manager') as cm_func:
            
            repo_cls.return_value = mock_token_repo
            cm_func.return_value = mock_connection_manager
            
            service = SessionService(mock_db)
            # Ensure our mocks are attached
            service.token_repo = mock_token_repo 
            service.connection_manager = mock_connection_manager
            
            yield service

    def test_get_active_channels(self, session_service, mock_connection_manager):
        mock_connection_manager.get_active_channels.return_value = ["test_channel", "12345"]
        
        channels = session_service.get_active_channels()
        
        assert len(channels) == 2
        assert channels[0]['channel_name'] == "test_channel"
        assert channels[0]['platform'] == "twitch"
        assert channels[1]['channel_name'] == "12345"
        assert channels[1]['platform'] == "vk"

    def test_get_active_sessions_details(self, session_service, mock_connection_manager):
        mock_connection_manager.get_active_sessions.return_value = {
            "channel1": {"sess1", "sess2"}
        }
        
        sessions = session_service.get_active_sessions_details()
        
        assert len(sessions) == 1
        assert sessions[0]['channel_name'] == "channel1"
        assert sessions[0]['session_count'] == 2

    def test_disconnect_channel(self, session_service, mock_connection_manager):
        mock_connection_manager.remove_active_session.return_value = True
        
        result = session_service.disconnect_channel("channel1", admin_id=1)
        
        assert result is True
        mock_connection_manager.remove_active_session.assert_called_with("channel1", "admin_disconnect")

    def test_get_user_tokens(self, session_service, mock_token_repo):
        # Mock tokens
        t1 = Mock(spec=UserToken)
        t1.id = 1
        t1.platform = "twitch"
        t1.created_at = datetime.now()
        t1.expires_at = None
        t1.is_active = True
        
        mock_token_repo.get_all_by_user.return_value = [t1]
        
        tokens = session_service.get_user_tokens(user_id=1)
        
        assert len(tokens) == 1
        assert tokens[0]['platform'] == "twitch"
        mock_token_repo.get_all_by_user.assert_called_with(1)

    def test_refresh_token_success(self, session_service, mock_token_repo, mock_db):
        token = Mock(spec=UserToken)
        token.id = 1
        token.user_id = 10
        
        mock_token_repo.get_by_id.return_value = token
        
        result = session_service.refresh_token(token_id=1, user_id=10)
        
        assert result is True
        mock_db.commit.assert_called_once()
        # Ensure created_at was updated (hard to check exact value but can check attribution)
        # assert token.created_at ... 

    def test_refresh_token_access_denied(self, session_service, mock_token_repo):
        token = Mock(spec=UserToken)
        token.id = 1
        token.user_id = 10
        
        mock_token_repo.get_by_id.return_value = token
        
        with pytest.raises(ValueError):
            session_service.refresh_token(token_id=1, user_id=999) # Wrong user

    def test_refresh_token_not_found(self, session_service, mock_token_repo):
        mock_token_repo.get_by_id.return_value = None
        
        result = session_service.refresh_token(token_id=1, user_id=10)
        
        assert result is False

    def test_get_token_owner(self, session_service, mock_token_repo):
        token = Mock(spec=UserToken)
        token.user_id = 55
        mock_token_repo.get_by_id.return_value = token
        
        owner_id = session_service.get_token_owner(1)
        assert owner_id == 55
