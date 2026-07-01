from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.database import User
from services.platform_sync_service import PlatformSyncService


@pytest.mark.asyncio
async def test_sync_vk_roles_updates_owner_channel_and_display_name_from_api():
    service = PlatformSyncService()
    user = User(
        id=1,
        vk_username="Legacy Name",
        vk_channel_name=None,
        vk_is_owner=False,
        vk_is_moderator=True,
    )
    db = MagicMock()
    token = SimpleNamespace(access_token="encrypted-token", refresh_token="refresh-token", scopes=["chat:read"])

    with (
        patch("services.platform_sync_service.UserTokenRepository") as token_repo_cls,
        patch("integrations.vk.oauth.VKOAuth"),
        patch("integrations.vk.client.VKClient") as vk_client_cls,
        patch("services.user_service.UserService") as user_service_cls,
    ):
        token_repo_cls.return_value.get_active_token.return_value = token
        user_service_cls.return_value.decrypt_access_token.return_value = "decrypted-token"
        vk_client_cls.return_value.get_current_user = AsyncMock(return_value={
            "id": "42",
            "nick": "StreamerNick",
            "channel": {
                "url": "https://live.vkvideo.ru/streamer_slug",
            },
        })

        result = await service._sync_vk_roles(user, db)

    assert result is True
    assert user.vk_username == "StreamerNick"
    assert user.vk_channel_name == "streamer_slug"
    assert user.vk_is_owner is True
    assert user.vk_is_moderator is False
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_sync_vk_roles_preserves_explicit_moderator_without_owner_channel():
    service = PlatformSyncService()
    user = User(
        id=2,
        vk_username="ExistingName",
        vk_channel_name=None,
        vk_is_owner=True,
        vk_is_moderator=False,
    )
    db = MagicMock()
    token = SimpleNamespace(access_token="encrypted-token", refresh_token=None, scopes=["chat:read"])

    with (
        patch("services.platform_sync_service.UserTokenRepository") as token_repo_cls,
        patch("integrations.vk.oauth.VKOAuth"),
        patch("integrations.vk.client.VKClient") as vk_client_cls,
        patch("services.user_service.UserService") as user_service_cls,
    ):
        token_repo_cls.return_value.get_active_token.return_value = token
        user_service_cls.return_value.decrypt_access_token.return_value = "decrypted-token"
        vk_client_cls.return_value.get_current_user = AsyncMock(return_value={
            "id": "99",
            "login": "ModeratorLogin",
            "is_moderator": True,
        })

        result = await service._sync_vk_roles(user, db)

    assert result is True
    assert user.vk_username == "ModeratorLogin"
    assert user.vk_channel_name is None
    assert user.vk_is_owner is False
    assert user.vk_is_moderator is True
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_sync_vk_roles_normalizes_stored_channel_when_api_has_no_channel():
    service = PlatformSyncService()
    user = User(
        id=3,
        vk_username="https://live.vkvideo.ru/legacy_slug",
        vk_channel_name="https://live.vkvideo.ru/stored_slug",
        vk_is_owner=False,
        vk_is_moderator=True,
    )
    db = MagicMock()
    token = SimpleNamespace(access_token="encrypted-token", refresh_token=None, scopes=["chat:read"])

    with (
        patch("services.platform_sync_service.UserTokenRepository") as token_repo_cls,
        patch("integrations.vk.oauth.VKOAuth"),
        patch("integrations.vk.client.VKClient") as vk_client_cls,
        patch("services.user_service.UserService") as user_service_cls,
    ):
        token_repo_cls.return_value.get_active_token.return_value = token
        user_service_cls.return_value.decrypt_access_token.return_value = "decrypted-token"
        vk_client_cls.return_value.get_current_user = AsyncMock(return_value={
            "id": "77",
            "screen_name": "FreshDisplayName",
        })

        result = await service._sync_vk_roles(user, db)

    assert result is True
    assert user.vk_username == "FreshDisplayName"
    assert user.vk_channel_name == "stored_slug"
    assert user.vk_is_owner is True
    assert user.vk_is_moderator is False
    db.commit.assert_called_once()
