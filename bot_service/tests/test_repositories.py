# tests/test_repositories.py
"""
Tests for TTS Repository Layer.
Tests CRUD operations for new Clean Architecture repositories.
"""
import pytest
from sqlalchemy.orm import Session

from repositories.tts_settings_repository import TTSSettingsRepository
from repositories.audio_settings_repository import AudioSettingsRepository
from repositories.chat_message_repository import ChatMessageRepository
from repositories.filtered_word_repository import FilteredWordRepository
from repositories.local_tts_repository import LocalTTSRepository
from repositories.blocked_user_repository import BlockedUserRepository
from models.analytics import ChatMessage
from models.tts import TTSUserSettings, AudioSettings, FilteredWord, LocalTTSEndpoint, TTSBlockedUser


class TestTTSSettingsRepository:
    """Tests for TTSSettingsRepository."""
    
    def test_get_or_create_new_user(self, db: Session, test_user):
        """Should create default settings for new user."""
        repo = TTSSettingsRepository(db)
        settings = repo.get_or_create(user_id=test_user.id)
        
        assert settings is not None
        assert settings.user_id == test_user.id
        assert settings.engine == 'gtts'  # Default
        assert settings.voice == 'default_voice'  # Default
    
    def test_get_or_create_existing_user(self, db: Session, test_user):
        """Should return existing settings."""
        repo = TTSSettingsRepository(db)
        
        # Create initial settings
        settings1 = repo.get_or_create(user_id=test_user.id)
        settings1_id = settings1.id
        
        # Get again - should be same record
        settings2 = repo.get_or_create(user_id=test_user.id)
        
        assert settings2.id == settings1_id
    
    def test_update_settings(self, db: Session, test_user):
        """Should update TTS settings."""
        repo = TTSSettingsRepository(db)
        settings = repo.get_or_create(user_id=test_user.id)
        
        updated = repo.update_settings(settings, {
            'engine': 'f5tts',
            'max_message_length': 1000
        })
        
        assert updated.engine == 'f5tts'
        assert updated.max_message_length == 1000
    
    def test_get_settings_dict(self, db: Session, test_user):
        """Should convert settings to dict."""
        repo = TTSSettingsRepository(db)
        settings = repo.get_or_create(user_id=test_user.id)
        
        settings_dict = repo.get_settings_dict(settings)
        
        assert 'engine' in settings_dict
        assert 'voice' in settings_dict
        assert 'enable_7tv' in settings_dict
        assert 'gcloud_voices' in settings_dict


class TestAudioSettingsRepository:
    """Tests for AudioSettingsRepository."""
    
    def test_get_or_create(self, db: Session, test_user):
        """Should create default audio settings."""
        repo = AudioSettingsRepository(db)
        settings = repo.get_or_create(test_user.id)
        
        assert settings.user_id == test_user.id
        assert settings.website_volume == 50
        assert settings.obs_volume == 50
    
    def test_update_volume(self, db: Session, test_user):
        """Should update volume values."""
        repo = AudioSettingsRepository(db)
        
        updated = repo.update_volume(test_user.id, website_volume=75)
        
        assert updated.website_volume == 75
        assert updated.obs_volume == 50
    
    def test_volume_bounds(self, db: Session, test_user):
        """Should clamp volume to 0-100 range."""
        repo = AudioSettingsRepository(db)
        
        # Test upper bound
        updated = repo.update_volume(test_user.id, website_volume=150)
        assert updated.website_volume == 100
        
        # Test lower bound
        updated = repo.update_volume(test_user.id, website_volume=-10)
        assert updated.website_volume == 0


class TestFilteredWordRepository:
    """Tests for FilteredWordRepository."""
    
    def test_add_word(self, db: Session, test_user):
        """Should add a filtered word."""
        repo = FilteredWordRepository(db)
        
        word = repo.add_word('badword', 'all', user_id=test_user.id)
        
        assert word is not None
        assert word.word == 'badword'
        assert word.platform == 'all'
    
    def test_add_duplicate_word(self, db: Session, test_user):
        """Should not add duplicate word."""
        repo = FilteredWordRepository(db)
        
        repo.add_word('badword', 'all', user_id=test_user.id)
        duplicate = repo.add_word('badword', 'all', user_id=test_user.id)
        
        assert duplicate is None  # Should return None for duplicate
    
    def test_remove_word(self, db: Session, test_user):
        """Should soft-delete a filtered word."""
        repo = FilteredWordRepository(db)
        
        word = repo.add_word('badword', 'all', user_id=test_user.id)
        result = repo.remove_word(word.id, user_id=test_user.id)
        
        assert result is True
        
        # Should not appear in list
        words = repo.get_words_list(user_id=test_user.id)
        assert len(words) == 0


class TestLocalTTSRepository:
    """Tests for LocalTTSRepository."""
    
    def test_create_endpoint(self, db: Session, test_user):
        """Should create local TTS endpoint."""
        repo = LocalTTSRepository(db)
        
        endpoint = repo.create_or_update(
            endpoint_url='http://localhost:5000',
            user_id=test_user.id
        )
        
        assert endpoint.endpoint_url == 'http://localhost:5000'
        assert endpoint.user_id == test_user.id
    
    def test_update_health_status(self, db: Session, test_user):
        """Should update health status."""
        repo = LocalTTSRepository(db)
        
        endpoint = repo.create_or_update(
            endpoint_url='http://localhost:5000',
            user_id=test_user.id
        )
        
        updated = repo.update_health_status(
            endpoint,
            is_healthy=True,
            tts_version='1.0.0'
        )
        
        assert updated.is_healthy is True
        assert updated.tts_version == '1.0.0'
        assert updated.health_check_failures == 0


class TestBlockedUserRepository:
    """Tests for BlockedUserRepository."""
    
    def test_block_user(self, db: Session, test_user):
        """Should block a user from TTS."""
        repo = BlockedUserRepository(db)
        
        blocked = repo.block_user(
            channel_name='test_channel',
            platform='twitch',
            username='bad_user',
            user_id=test_user.id
        )
        
        assert blocked is not None
        assert blocked.username == 'bad_user'
    
    def test_is_blocked(self, db: Session, test_user):
        """Should check if user is blocked."""
        repo = BlockedUserRepository(db)
        
        # Not blocked initially
        assert repo.is_blocked('test_channel', 'twitch', 'bad_user', user_id=test_user.id) is False
        
        # Block user
        repo.block_user('test_channel', 'twitch', 'bad_user', user_id=test_user.id)
        
        # Now should be blocked
        assert repo.is_blocked('test_channel', 'twitch', 'bad_user', user_id=test_user.id) is True
    
    def test_unblock_user(self, db: Session, test_user):
        """Should unblock a user."""
        repo = BlockedUserRepository(db)
        
        repo.block_user('test_channel', 'twitch', 'bad_user', user_id=test_user.id)
        result = repo.unblock_user('test_channel', 'twitch', 'bad_user', user_id=test_user.id)
        
        assert result is True
        assert repo.is_blocked('test_channel', 'twitch', 'bad_user', user_id=test_user.id) is False


class TestChatMessageRepository:
    """Tests for ChatMessageRepository."""

    def test_create_persists_author_id(self, db: Session, test_user):
        """Should store author_id when chat identity is available."""
        repo = ChatMessageRepository(db)

        message = repo.create(
            user_id=test_user.id,
            channel_name='test_channel',
            platform='twitch',
            message='hello chat',
            author_username='viewer1',
            author_id='123456',
        )

        stored = db.query(ChatMessage).filter(ChatMessage.id == message.id).one()
        assert stored.author_username == 'viewer1'
        assert stored.author_id == '123456'
