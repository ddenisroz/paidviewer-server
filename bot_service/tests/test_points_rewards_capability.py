from fastapi import HTTPException


class _RewardsForbiddenService:
    async def get_rewards(self, user_id, platform, db):
        raise HTTPException(status_code=403, detail="Authentication failed")


class _RewardsAvailableService:
    async def get_rewards(self, user_id, platform, db):
        return [{"id": "reward-1", "title": "Test reward", "cost": 100}]


class _VkRewardsUnavailableService:
    async def get_rewards(self, user_id, platform, db):
        raise HTTPException(
            status_code=403,
            detail="У токена VK Live не хватает прав: channel:points:rewards. Переавторизуйте интеграцию VK Live.",
        )


def test_twitch_rewards_forbidden_returns_disabled_capability(authenticated_client, monkeypatch):
    monkeypatch.setattr(
        "api.points.twitch_routes.get_platform_rewards_service",
        lambda: _RewardsForbiddenService(),
    )

    response = authenticated_client.get("/api/points/rewards/twitch")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["platform"] == "twitch"
    assert data["rewards"] == []
    assert data["capability"] == {
        "can_create": False,
        "reason": "Twitch разрешает создавать награды только для каналов со статусом Affiliate или Partner.",
        "required_role": "affiliate_or_partner",
        "platform": "twitch",
    }


def test_twitch_rewards_available_returns_enabled_capability(authenticated_client, monkeypatch):
    monkeypatch.setattr(
        "api.points.twitch_routes.get_platform_rewards_service",
        lambda: _RewardsAvailableService(),
    )

    response = authenticated_client.get("/api/points/rewards/twitch")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["rewards"] == [{"id": "reward-1", "title": "Test reward", "cost": 100}]
    assert data["capability"] == {
        "can_create": True,
        "reason": None,
        "required_role": "affiliate_or_partner",
        "platform": "twitch",
    }


def test_vk_rewards_forbidden_returns_disabled_capability(authenticated_client, monkeypatch):
    monkeypatch.setattr(
        "api.points.vk_routes.get_platform_rewards_service",
        lambda: _VkRewardsUnavailableService(),
    )

    response = authenticated_client.get("/api/points/rewards/vk")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["platform"] == "vk"
    assert data["rewards"] == []
    assert data["capability"] == {
        "can_create": False,
        "reason": "У токена VK Live не хватает прав: channel:points:rewards. Переавторизуйте интеграцию VK Live.",
        "required_role": "channel_owner",
        "platform": "vk",
    }
