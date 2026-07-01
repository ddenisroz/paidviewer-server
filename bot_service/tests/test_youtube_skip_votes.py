import logging

import pytest

from bots.mixins.queue_handler_mixin import QueueHandlerMixin
from models.commands import BotCommand
from models.youtube import YouTubeQueue
from services.youtube.skip_vote_store import skip_vote_store
from utils.platform_role_checker import PlatformRoleChecker


def _queue_item(*, user_id: int, video_id: str, title: str, position: int = 1) -> YouTubeQueue:
    return YouTubeQueue(
        user_id=user_id,
        video_url=f"https://www.youtube.com/watch?v={video_id}",
        video_id=video_id,
        title=title,
        channel_name="test_user",
        platform="twitch",
        requester_name="tester",
        requester_id="tester",
        position=position,
        status="pending",
    )


class _DummyAuthor:
    def __init__(self, name: str, *, is_mod: bool = False, is_broadcaster: bool = False):
        self.name = name
        self.id = name
        self.is_mod = is_mod
        self.is_broadcaster = is_broadcaster
        self.is_vip = False
        self.is_subscriber = False
        self.badges = []


class _DummyChannel:
    def __init__(self, name: str):
        self.name = name


class _DummyContext:
    def __init__(self, channel_name: str, author_name: str, *, is_mod: bool = False):
        self.author = _DummyAuthor(author_name, is_mod=is_mod)
        self.channel = _DummyChannel(channel_name)
        self.sent_messages: list[str] = []

    async def send(self, message: str) -> None:
        self.sent_messages.append(message)


class _DummyQueueHandler(QueueHandlerMixin):
    def __init__(self):
        self.logger = logging.getLogger("test.queue_handler")
        self.role_checker = PlatformRoleChecker()


@pytest.fixture(autouse=True)
def _reset_skip_votes():
    skip_vote_store._votes.clear()
    yield
    skip_vote_store._votes.clear()


@pytest.mark.asyncio
async def test_vote_skip_requires_threshold(db, test_user):
    db.add(
        BotCommand(
            user_id=test_user.id,
            command_name="skip",
            command_type="override",
            platforms="twitch,vk",
            allowed_roles="all",
            extra_settings={"skip_votes_required": 2},
        )
    )
    db.add(_queue_item(user_id=test_user.id, video_id="votevideo1", title="Vote Video"))
    db.commit()

    handler = _DummyQueueHandler()
    first_ctx = _DummyContext(test_user.twitch_username, "viewer_one")
    second_ctx = _DummyContext(test_user.twitch_username, "viewer_two")

    await handler._handle_skip(first_ctx, None, "", "twitch", db)
    queue_after_first_vote = db.query(YouTubeQueue).filter(YouTubeQueue.user_id == test_user.id).first()

    assert "[VOTE]" in first_ctx.sent_messages[-1]
    assert queue_after_first_vote.status == "pending"
    assert skip_vote_store.get_vote_count(test_user.id, queue_after_first_vote.id) == 1

    await handler._handle_skip(second_ctx, None, "", "twitch", db)
    db.expire_all()
    queue_after_second_vote = db.query(YouTubeQueue).filter(YouTubeQueue.user_id == test_user.id).first()

    assert "[SKIP]" in second_ctx.sent_messages[-1]
    assert queue_after_second_vote.status == "played"
    assert skip_vote_store.get_vote_count(test_user.id, queue_after_second_vote.id) == 0


@pytest.mark.asyncio
async def test_one_skip_vote_allows_regular_viewer(db, test_user):
    db.add(
        BotCommand(
            user_id=test_user.id,
            command_name="skip",
            command_type="override",
            platforms="twitch,vk",
            allowed_roles="all",
            extra_settings={"skip_votes_required": 1},
        )
    )
    db.add(_queue_item(user_id=test_user.id, video_id="oneskip1", title="One Skip Video"))
    db.commit()

    handler = _DummyQueueHandler()
    ctx = _DummyContext(test_user.twitch_username, "regular_viewer", is_mod=False)

    await handler._handle_skip(ctx, None, "", "twitch", db)
    db.expire_all()
    queue_after_vote = db.query(YouTubeQueue).filter(YouTubeQueue.user_id == test_user.id).first()

    assert "[SKIP]" in ctx.sent_messages[-1]
    assert "Only moderators" not in ctx.sent_messages[-1]
    assert queue_after_vote.status == "played"


@pytest.mark.asyncio
async def test_skip_votes_dedupe_by_viewer_id(db, test_user):
    db.add(
        BotCommand(
            user_id=test_user.id,
            command_name="skip",
            command_type="override",
            platforms="twitch,vk",
            allowed_roles="all",
            extra_settings={"skip_votes_required": 2},
        )
    )
    queue_item = _queue_item(user_id=test_user.id, video_id="dedupe1", title="Dedupe Video")
    db.add(queue_item)
    db.commit()
    db.refresh(queue_item)

    handler = _DummyQueueHandler()
    first_ctx = _DummyContext(test_user.twitch_username, "viewer_name_a")
    second_ctx = _DummyContext(test_user.twitch_username, "viewer_name_b")
    first_ctx.author.id = "same-viewer-id"
    second_ctx.author.id = "same-viewer-id"

    await handler._handle_skip(first_ctx, None, "", "twitch", db)
    await handler._handle_skip(second_ctx, None, "", "twitch", db)

    assert "[INFO] You already voted" in second_ctx.sent_messages[-1]
    assert skip_vote_store.get_vote_count(test_user.id, queue_item.id) == 1


def test_youtube_queue_api_returns_skip_votes(authenticated_client, db, test_user):
    db.add(
        BotCommand(
            user_id=test_user.id,
            command_name="skip",
            command_type="override",
            platforms="twitch,vk",
            allowed_roles="all",
            extra_settings={"skip_votes_required": 3},
        )
    )
    queue_item = _queue_item(user_id=test_user.id, video_id="apiqueue1", title="API Queue Video")
    db.add(queue_item)
    db.commit()
    db.refresh(queue_item)

    skip_vote_store.add_vote(test_user.id, queue_item.id, "viewer_one")

    response = authenticated_client.get("/api/youtube/queue")

    assert response.status_code == 200
    payload = response.json()
    assert payload["skip_votes"] == {
        "current": 1,
        "required": 3,
        "video_id": queue_item.id,
    }
