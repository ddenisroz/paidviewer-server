from models import User
from models.youtube import YouTubeQueue
from services.youtube.queue_service import QueueService
import pytest


def _queue_item(
    *,
    user_id: int | None = None,
    session_id: str | None = None,
    video_id: str,
    title: str,
    position: int,
    status: str = "pending",
) -> YouTubeQueue:
    return YouTubeQueue(
        user_id=user_id,
        session_id=session_id,
        video_url=f"https://www.youtube.com/watch?v={video_id}",
        video_id=video_id,
        title=title,
        channel_name="queue_owner",
        platform="twitch",
        requester_name="tester",
        requester_id="tester",
        position=position,
        status=status,
    )


def test_get_user_queue_returns_only_pending_items_for_user(db, test_user):
    other_user = User(twitch_username="other_queue_owner", role="user", is_active=True)
    db.add(other_user)
    db.commit()
    db.refresh(other_user)

    db.add_all(
        [
            _queue_item(user_id=test_user.id, video_id="userpending1", title="User Pending 1", position=1),
            _queue_item(
                user_id=test_user.id,
                video_id="userplayed1",
                title="User Played",
                position=2,
                status="played",
            ),
            _queue_item(user_id=other_user.id, video_id="otherpending1", title="Other Pending", position=1),
        ]
    )
    db.commit()

    queue = QueueService().get_user_queue(test_user.id, db=db)

    assert [item["video_id"] for item in queue] == ["userpending1"]


def test_get_queue_supports_legacy_positional_db_argument(db, test_user):
    db.add(
        _queue_item(
            user_id=test_user.id,
            video_id="legacycompat1",
            title="Legacy Compat Queue",
            position=1,
        )
    )
    db.commit()

    queue = QueueService().get_queue(test_user.id, db)

    assert len(queue) == 1
    assert queue[0]["video_id"] == "legacycompat1"


def test_reorder_queue_items_rebuilds_positions_around_current_video(db, test_user):
    current_item = _queue_item(
        user_id=test_user.id,
        video_id="currentvideo1",
        title="Current Video",
        position=1,
    )
    second_item = _queue_item(
        user_id=test_user.id,
        video_id="nextvideo2",
        title="Next Video",
        position=2,
    )
    third_item = _queue_item(
        user_id=test_user.id,
        video_id="latervideo3",
        title="Later Video",
        position=3,
    )
    db.add_all([current_item, second_item, third_item])
    db.commit()
    db.refresh(current_item)
    db.refresh(second_item)
    db.refresh(third_item)

    success = QueueService().reorder_queue_items(
        test_user.id,
        third_item.id,
        second_item.id,
        db=db,
    )

    assert success is True

    reordered_items = (
        db.query(YouTubeQueue)
        .filter(YouTubeQueue.user_id == test_user.id, YouTubeQueue.status == "pending")
        .order_by(YouTubeQueue.position.asc())
        .all()
    )

    assert [item.video_id for item in reordered_items] == [
        "currentvideo1",
        "latervideo3",
        "nextvideo2",
    ]
    assert [item.position for item in reordered_items] == [1, 2, 3]


def test_reorder_queue_api_updates_pending_order(authenticated_client, db, test_user):
    current_item = _queue_item(
        user_id=test_user.id,
        video_id="api_current_1",
        title="API Current",
        position=1,
    )
    second_item = _queue_item(
        user_id=test_user.id,
        video_id="api_second_2",
        title="API Second",
        position=2,
    )
    third_item = _queue_item(
        user_id=test_user.id,
        video_id="api_third_3",
        title="API Third",
        position=3,
    )
    db.add_all([current_item, second_item, third_item])
    db.commit()
    db.refresh(second_item)
    db.refresh(third_item)

    response = authenticated_client.post(
        "/api/youtube/queue/reorder",
        json={
            "active_queue_id": third_item.id,
            "over_queue_id": second_item.id,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True

    reordered_items = (
        db.query(YouTubeQueue)
        .filter(YouTubeQueue.user_id == test_user.id, YouTubeQueue.status == "pending")
        .order_by(YouTubeQueue.position.asc())
        .all()
    )

    assert [item.video_id for item in reordered_items] == [
        "api_current_1",
        "api_third_3",
        "api_second_2",
    ]


@pytest.mark.asyncio
async def test_paid_priority_video_takes_next_slot(db, test_user, monkeypatch):
    async def _no_broadcast(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "services.youtube.queue_service.broadcast_youtube_queue_update",
        _no_broadcast,
    )

    db.add_all(
        [
            _queue_item(
                user_id=test_user.id,
                video_id="currentvideo",
                title="Current Video",
                position=1,
            ),
            _queue_item(
                user_id=test_user.id,
                video_id="normalnext1",
                title="Normal Next",
                position=2,
            ),
            _queue_item(
                user_id=test_user.id,
                video_id="normallater2",
                title="Normal Later",
                position=3,
            ),
        ]
    )
    db.commit()

    service = QueueService()
    service.youtube_service.is_valid_youtube_url = lambda _url: True

    async def _video_info(_url):
        return {
            "video_id": "paidvideo11",
            "title": "Paid Video",
            "duration": 123,
            "thumbnail_url": "https://img.youtube.com/vi/paidvideo11/hqdefault.jpg",
        }

    service.youtube_service.get_video_info = _video_info

    result = await service.add_video_to_user_queue(
        user_id=test_user.id,
        video_url="https://www.youtube.com/watch?v=paidvideo11",
        channel_name="test_user",
        platform="donationalerts",
        requester_name="Paid Donor",
        requester_id="donor-1",
        is_paid=True,
        paid_source="donationalerts",
        paid_amount=250.0,
        paid_currency="RUB",
        source_alert_id="alert-1",
        priority_next=True,
        db=db,
    )

    assert result["success"] is True
    assert result["queue_item"]["position"] == 2
    assert result["queue_item"]["paid_source"] == "donationalerts"

    reordered_items = (
        db.query(YouTubeQueue)
        .filter(YouTubeQueue.user_id == test_user.id, YouTubeQueue.status == "pending")
        .order_by(YouTubeQueue.position.asc())
        .all()
    )

    assert [item.video_id for item in reordered_items] == [
        "currentvideo",
        "paidvideo11",
        "normalnext1",
        "normallater2",
    ]
    assert reordered_items[1].is_paid is True
    assert reordered_items[1].paid_amount == 250.0


@pytest.mark.asyncio
async def test_add_video_to_queue_uses_owner_name_and_broadcasts_once(db, test_user, monkeypatch):
    calls: list[int] = []

    async def _broadcast(user_id: int):
        calls.append(user_id)

    monkeypatch.setattr(
        "services.youtube.queue_service.broadcast_youtube_queue_update",
        _broadcast,
    )

    service = QueueService()
    service.youtube_service.is_valid_youtube_url = lambda _url: True

    async def _video_info(_url):
        return {
            "video_id": "ownernamed1",
            "title": "Owner Named",
            "duration": "3:33",
            "thumbnail_url": "https://img.youtube.com/vi/ownernamed1/hqdefault.jpg",
        }

    service.youtube_service.get_video_info = _video_info

    result = await service.add_video_to_user_queue(
        user_id=test_user.id,
        video_url="https://www.youtube.com/watch?v=ownernamed1",
        channel_name="web_interface",
        platform="web",
        requester_name=f"User_{test_user.id}",
        requester_id=str(test_user.id),
        db=db,
    )

    assert result["success"] is True
    assert result["queue_item"]["requester_name"] == test_user.twitch_username
    assert calls == [test_user.id]


@pytest.mark.asyncio
async def test_paid_priority_does_not_shift_queue_when_points_deduction_fails(db, test_user, monkeypatch):
    async def _no_broadcast(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "services.youtube.queue_service.broadcast_youtube_queue_update",
        _no_broadcast,
    )

    db.add_all(
        [
            _queue_item(
                user_id=test_user.id,
                video_id="currentvideo",
                title="Current Video",
                position=1,
            ),
            _queue_item(
                user_id=test_user.id,
                video_id="normalnext1",
                title="Normal Next",
                position=2,
            ),
        ]
    )
    db.commit()

    service = QueueService()
    service.youtube_service.is_valid_youtube_url = lambda _url: True

    async def _video_info(_url):
        return {
            "video_id": "paidvideo12",
            "title": "Paid Video",
            "duration": 123,
            "thumbnail_url": "https://img.youtube.com/vi/paidvideo12/hqdefault.jpg",
        }

    service.youtube_service.get_video_info = _video_info

    result = await service.add_video_to_user_queue(
        user_id=test_user.id,
        video_url="https://www.youtube.com/watch?v=paidvideo12",
        channel_name="test_user",
        platform="donationalerts",
        requester_name="Paid Donor",
        requester_id="donor-2",
        is_paid=True,
        points_cost=500,
        paid_source="donationalerts",
        paid_amount=500.0,
        paid_currency="RUB",
        source_alert_id="alert-2",
        priority_next=True,
        db=db,
    )

    assert result["success"] is False
    assert "Not enough points" in result["error"]

    pending_items = (
        db.query(YouTubeQueue)
        .filter(YouTubeQueue.user_id == test_user.id, YouTubeQueue.status == "pending")
        .order_by(YouTubeQueue.position.asc())
        .all()
    )

    assert [item.video_id for item in pending_items] == ["currentvideo", "normalnext1"]
    assert [item.position for item in pending_items] == [1, 2]


@pytest.mark.asyncio
async def test_queue_limit_is_enforced_before_upstream_lookup(db, test_user, monkeypatch):
    async def _no_broadcast(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "services.youtube.queue_service.broadcast_youtube_queue_update",
        _no_broadcast,
    )

    db.add_all(
        [
            _queue_item(
                user_id=test_user.id,
                video_id=f"video-{index}",
                title=f"Video {index}",
                position=index + 1,
            )
            for index in range(10)
        ]
    )
    db.commit()

    service = QueueService()
    service.youtube_service.is_valid_youtube_url = lambda _url: True

    async def _should_not_be_called(_url):
        raise AssertionError("Upstream lookup must not run when queue is already full")

    service.youtube_service.get_video_info = _should_not_be_called

    result = await service.add_video_to_user_queue(
        user_id=test_user.id,
        video_url="https://www.youtube.com/watch?v=queuefull99",
        channel_name="web_interface",
        platform="web",
        requester_name="tester",
        requester_id="tester",
        db=db,
    )

    assert result["success"] is False
    assert "Queue limit reached" in result["error"]
