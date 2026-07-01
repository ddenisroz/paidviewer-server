import pytest

from core.database import User, UserToken
from repositories.user_token_repository import UserTokenRepository


def test_upsert_rejects_platform_identity_linked_to_another_user(db_session):
    first = User(id=101, is_active=True, twitch_username="first_owner")
    second = User(id=102, is_active=True, twitch_username="second_owner")
    db_session.add_all([first, second])
    db_session.commit()

    repo = UserTokenRepository(db_session)
    repo.upsert(
        user_id=first.id,
        platform="twitch",
        platform_user_id="same-twitch-id",
        access_token="first-token",
    )

    with pytest.raises(ValueError, match="already linked"):
        repo.upsert(
            user_id=second.id,
            platform="twitch",
            platform_user_id="same-twitch-id",
            access_token="second-token",
        )

    rows = db_session.query(UserToken).filter(
        UserToken.platform == "twitch",
        UserToken.platform_user_id == "same-twitch-id",
    ).all()
    assert len(rows) == 1
    assert rows[0].user_id == first.id
