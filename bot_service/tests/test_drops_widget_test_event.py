from core.database import DropsQuality, DropsReward


class _FakeDropsWidgetManager:
    def __init__(self, delivered: int = 1):
        self.delivered = delivered
        self.calls = []

    async def send_to_user(self, user_id, message, client_roles=None, exclude_presence_only=False):
        self.calls.append(
            {
                "user_id": user_id,
                "message": message,
                "client_roles": client_roles,
                "exclude_presence_only": exclude_presence_only,
            }
        )
        return self.delivered


def _seed_quality(db, *, quality_id: int = 1, name: str = "Common"):
    quality = DropsQuality(id=quality_id, name=name, color="#9ca3af", weight=100)
    db.add(quality)
    db.commit()
    return quality


def test_widget_test_event_sends_backend_selected_reward(authenticated_client, db, test_user, monkeypatch):
    quality = _seed_quality(db)
    reward = DropsReward(
        user_id=test_user.id,
        channel_name=test_user.twitch_username,
        platform="twitch",
        name="Coin Pack",
        description="Test reward",
        quality_id=quality.id,
        weight=100,
        reward_type="points",
        reward_value="100",
        is_active=True,
    )
    db.add(reward)
    db.commit()

    fake_manager = _FakeDropsWidgetManager(delivered=1)
    import services.memory_websocket_manager as memory_websocket_manager

    monkeypatch.setattr(memory_websocket_manager, "get_memory_websocket_manager", lambda: fake_manager)

    response = authenticated_client.post(
        f"/api/drops/widget/test-event/{test_user.twitch_username}",
        json={"quality": "common"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["delivered"] == 1
    assert payload["data"]["reward_name"] == "Coin Pack"
    assert fake_manager.calls[0]["user_id"] == test_user.id
    assert fake_manager.calls[0]["client_roles"] == {"drops_widget"}
    event = fake_manager.calls[0]["message"]
    assert event["type"] == "drops"
    assert event["event"] == "reward_received"
    assert event["data"]["quality"] == "common"
    assert event["data"]["reward_name"] == "Coin Pack"
    assert event["data"]["reward"] == "Coin Pack"


def test_widget_test_event_uses_fallback_when_quality_has_no_rewards(authenticated_client, db, test_user, monkeypatch):
    _seed_quality(db, quality_id=2, name="Rare")
    fake_manager = _FakeDropsWidgetManager(delivered=0)
    import services.memory_websocket_manager as memory_websocket_manager

    monkeypatch.setattr(memory_websocket_manager, "get_memory_websocket_manager", lambda: fake_manager)

    response = authenticated_client.post(
        f"/api/drops/widget/test-event/{test_user.twitch_username}",
        json={"quality": "rare"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["delivered"] == 0
    event = fake_manager.calls[0]["message"]
    assert event["data"]["quality"] == "rare"
    assert event["data"]["reward_id"] == -1
    assert event["data"]["reward_name"]


def test_widget_test_event_rejects_unknown_quality(authenticated_client, test_user):
    response = authenticated_client.post(
        f"/api/drops/widget/test-event/{test_user.twitch_username}",
        json={"quality": "broken"},
    )

    assert response.status_code == 400
