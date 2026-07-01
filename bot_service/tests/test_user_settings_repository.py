# bot_service/tests/test_user_settings_repository.py
import pytest
from sqlalchemy.orm import Session
from repositories.user_settings_repository import UserSettingsRepository
from core.database import UserSettings, User
from core.datetime_utils import utcnow_naive

@pytest.fixture
def user_settings_repo(db_session: Session):
    return UserSettingsRepository(db_session)

def params_test_user(db: Session, **kwargs) -> User:
    """Local helper to create test user."""
    defaults = {
        "twitch_username": f"user_settings_test_{utcnow_naive().timestamp()}",
        "is_admin": False,
        "is_active": True,
        "role": "user"
    }
    defaults.update(kwargs)
    user = User(**defaults)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

class TestUserSettingsRepository:
    """Tests for UserSettingsRepository."""

    def test_create_and_get_by_user_id(self, user_settings_repo, db_session):
        """Test creating and retrieving settings for authenticated user."""
        # Create user manually to avoid fixture issues
        # Need date util for unique numeric username suffix if needed, but timestamp is fine
        from core.datetime_utils import utcnow_naive
        
        user = params_test_user(db_session, twitch_username="unique_user_1")

        # Create
        data = {"user_id": user.id, "chat_enabled": False}
        settings = user_settings_repo.create_default(data)
        
        assert settings.id is not None
        assert settings.user_id == user.id
        assert settings.chat_enabled is False
        
        # Get by user_id
        fetched = user_settings_repo.get_by_user_id(user.id)
        assert fetched is not None
        assert fetched.id == settings.id

        # Get by filters
        fetched_filter = user_settings_repo.get_by_filters({"user_id": user.id})
        assert fetched_filter is not None
        assert fetched_filter.id == settings.id

    def test_update_settings(self, user_settings_repo, db_session):
        """Test updating existing settings."""
        # Setup
        user = params_test_user(db_session, twitch_username="unique_user_2")
        data = {"user_id": user.id}
        settings = user_settings_repo.create_default(data)
        
        # Update
        update_data = {"chat_enabled": False, "obs_height": 900}
        updated = user_settings_repo.update(settings, update_data)
        
        assert updated.chat_enabled is False
        assert updated.obs_height == 900
        
        # Verify persistence
        fetched = user_settings_repo.get_by_user_id(user.id)
        assert fetched.chat_enabled is False
        assert fetched.obs_height == 900

    def test_get_non_existent(self, user_settings_repo):
        """Test getting non-existent settings returns None."""
        assert user_settings_repo.get_by_user_id(99999) is None
