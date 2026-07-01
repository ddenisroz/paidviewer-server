import asyncio

from auth.oauth_handler import OAuthHandler, OAuthUserData
from models.user import User
from platforms.vk import VKPlatform
from utils.platform_role_checker import PlatformRoleChecker


def test_oauth_handler_applies_vk_owner_profile():
    handler = OAuthHandler()
    user = User(vk_is_owner=False, vk_is_moderator=True)
    user_data = OAuthUserData(
        platform_user_id="42",
        avatar_url=None,
        access_token="access-token",
        refresh_token="refresh-token",
        expires_at=None,
        scopes=["chat:message:send"],
        username="Display Name",
        channel_name="https://live.vkvideo.ru/paidviewer",
    )

    handler._apply_vk_profile(user, user_data)

    assert user.vk_channel_name == "paidviewer"
    assert user.vk_username == "Display Name"
    assert user.vk_is_owner is True
    assert user.vk_is_moderator is False


def test_oauth_handler_clears_stale_vk_owner_when_channel_is_missing():
    handler = OAuthHandler()
    user = User(
        vk_username="old_display",
        vk_channel_name="stale_channel",
        vk_is_owner=True,
        vk_is_moderator=True,
    )
    user_data = OAuthUserData(
        platform_user_id="42",
        avatar_url=None,
        access_token="access-token",
        refresh_token="refresh-token",
        expires_at=None,
        scopes=["chat:message:send"],
        username="Display Name",
        channel_name=None,
    )

    handler._apply_vk_profile(user, user_data)

    assert user.vk_channel_name is None
    assert user.vk_username == "Display Name"
    assert user.vk_is_owner is False
    assert user.vk_is_moderator is False


def test_vk_role_checker_treats_matching_channel_slug_as_owner():
    roles = PlatformRoleChecker.get_vk_roles(
        {"name": "paidviewer"},
        "https://live.vkvideo.ru/paidviewer",
    )

    assert "owner" in roles
    assert "broadcaster" in roles


def test_vk_role_checker_respects_broadcaster_flag():
    roles = PlatformRoleChecker.get_vk_roles(
        {"nick": "viewer", "is_broadcaster": True},
        "streamer_channel",
    )

    assert "owner" in roles
    assert "broadcaster" in roles


def test_vk_platform_get_user_roles_uses_normalized_owner_and_moderator_flags(monkeypatch):
    class FakeQuery:
        def __init__(self, user):
            self._user = user

        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return self._user

    class FakeSession:
        def __init__(self, user):
            self._user = user

        def query(self, _model):
            return FakeQuery(self._user)

        def close(self):
            return None

    def fake_get_db():
        yield FakeSession(
            User(
                vk_username="Display Name",
                vk_channel_name="paidviewer",
                vk_is_owner=True,
                vk_is_moderator=True,
            )
        )

    monkeypatch.setattr("platforms.vk.get_db", fake_get_db)

    platform = VKPlatform()
    roles = asyncio.run(platform.get_user_roles("Display Name", "https://live.vkvideo.ru/paidviewer"))

    assert "owner" in roles
    assert "broadcaster" in roles
    assert "moderator" in roles


def test_vk_platform_get_user_roles_falls_back_to_doc_backed_chat_members(monkeypatch):
    class FakeQuery:
        def __init__(self, results):
            self._results = list(results)
            self._filtered = list(results)

        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return self._filtered[0] if self._filtered else None

    class FakeSession:
        def __init__(self):
            self._users = [
                User(
                    id=10,
                    vk_username="paidviewer",
                    vk_channel_name="paidviewer",
                    vk_is_owner=True,
                    vk_is_moderator=False,
                )
            ]

        def query(self, _model):
            return FakeQuery(self._users)

        def close(self):
            return None

    def fake_get_db():
        yield FakeSession()

    def fake_get_user_token(_self, _user_id, _platform, _db):
        return type(
            "TokenRecord",
            (),
            {
                "access_token": "encrypted-token",
                "refresh_token": "refresh-token",
                "scopes": ["chat:read"],
            },
        )()

    async def fake_get_chat_members(_self, _channel_name, _token_info, limit=200):
        assert limit == 200
        return [
            {
                "id": 321,
                "nick": "viewer_name",
                "is_owner": False,
                "is_moderator": True,
            }
        ]

    monkeypatch.setattr("platforms.vk.get_db", fake_get_db)
    monkeypatch.setattr("platforms.vk.UserService.get_user_token", fake_get_user_token)
    monkeypatch.setattr("platforms.vk.UserService.decrypt_access_token", lambda *_args, **_kwargs: "decrypted-token")
    monkeypatch.setattr("platforms.vk.VKClient.get_chat_members", fake_get_chat_members)

    platform = VKPlatform()
    roles = asyncio.run(platform.get_user_roles("viewer_name", "https://live.vkvideo.ru/paidviewer"))

    assert "moderator" in roles
    assert "viewer" not in roles
