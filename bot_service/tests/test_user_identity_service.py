"""Tests for authenticated-only UserIdentityService helpers."""

import pytest

from services.user_identity_service import UserIdentityService, UserType


class TestUserIdentityService:
    def test_get_user_type_authenticated(self):
        auth_user = {"id": 1, "username": "testuser"}
        user_type = UserIdentityService.get_user_type(auth_user)
        assert user_type == UserType.AUTHENTICATED

    def test_get_user_identifier_authenticated(self):
        auth_user = {"id": 1, "username": "testuser"}
        assert UserIdentityService.get_user_identifier(auth_user) == "1"

    def test_get_database_filters_authenticated(self):
        auth_user = {"id": 1, "username": "testuser"}
        assert UserIdentityService.get_database_filters(auth_user) == {"user_id": 1}

    def test_create_settings_record_data_authenticated(self):
        auth_user = {"id": 1, "username": "testuser"}
        assert UserIdentityService.create_settings_record_data(auth_user) == {"user_id": 1}

    def test_get_websocket_user_id_authenticated(self):
        auth_user = {"id": 7, "username": "testuser"}
        assert UserIdentityService.get_websocket_user_id(auth_user) == "7"

    def test_get_rate_limit_id_authenticated(self):
        auth_user = {"id": 9, "username": "testuser"}
        assert UserIdentityService.get_rate_limit_id(auth_user) == "9"

    def test_get_tts_channel_name_authenticated(self):
        auth_user = {"id": 1, "username": "testuser"}
        assert UserIdentityService.get_tts_channel_name(auth_user) == "user_1"

    def test_validate_user_data_authenticated_valid(self):
        auth_user = {"id": 1, "username": "testuser"}
        assert UserIdentityService.validate_user_data(auth_user) is True

    def test_validate_user_data_authenticated_invalid(self):
        auth_user = {"username": "testuser"}
        assert UserIdentityService.validate_user_data(auth_user) is False

    def test_validate_user_data_rejects_non_positive_id(self):
        assert UserIdentityService.validate_user_data({"id": 0}) is False
        assert UserIdentityService.validate_user_data({"id": -1}) is False

    def test_get_user_identifier_missing_id(self):
        with pytest.raises(ValueError, match="Authenticated user must have id"):
            UserIdentityService.get_user_identifier({"username": "testuser"})

    def test_get_user_identifier_non_numeric_id(self):
        with pytest.raises(ValueError, match="Authenticated user must have numeric id"):
            UserIdentityService.get_user_identifier({"id": "abc"})

    def test_get_user_identifier_non_positive_id(self):
        with pytest.raises(ValueError, match="Authenticated user must have positive id"):
            UserIdentityService.get_user_identifier({"id": -1})

