import pytest

from models import TTSUserSettings, UserToken


@pytest.mark.asyncio
async def test_donationalerts_webhook_adds_paid_youtube_video(client, db, test_user, monkeypatch):
    captured: dict = {}

    def _no_drops(self, **_kwargs):
        return None

    async def _no_memealerts(self, **_kwargs):
        return None

    async def _add_paid_video(self, **kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "queue_item": {
                "id": 42,
                "position": 2,
                "is_paid": True,
                "paid_source": "donationalerts",
            },
        }

    async def _get_video_info(self, _url):
        return {"video_id": "dQw4w9WgXcQ", "duration": "3:01"}

    monkeypatch.setattr(
        "services.drops.drops_service.DropsService.process_donation_drops_for_user",
        _no_drops,
    )
    monkeypatch.setattr(
        "services.memealerts_service.MemeAlertsService.process_donation_auto_grant",
        _no_memealerts,
    )
    monkeypatch.setattr(
        "services.youtube.queue_service.QueueService.add_video_to_user_queue",
        _add_paid_video,
    )
    monkeypatch.setattr(
        "services.youtube.youtube_service.YouTubeService.get_video_info",
        _get_video_info,
    )

    db.add(
        UserToken(
            user_id=test_user.id,
            platform="donationalerts",
            platform_user_id="da-streamer-1",
            access_token="token",
            auth_type="full",
        )
    )
    db.add(
        TTSUserSettings(
            user_id=test_user.id,
            youtube_settings={
                "donationalerts_video_enabled": True,
                "donationalerts_video_min_amount": 50,
                "donationalerts_video_priority_next": True,
            },
        )
    )
    db.commit()

    response = client.post(
        "/api/drops/donationalerts/webhook",
        json={
            "id": "alert-paid-1",
            "user_id": "da-streamer-1",
            "username": "Paid Donor",
            "amount": "250.50",
            "currency": "RUB",
            "message": "play this https://youtu.be/dQw4w9WgXcQ thanks",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["youtube"]["success"] is True
    assert captured["user_id"] == test_user.id
    assert captured["video_url"] == "https://youtu.be/dQw4w9WgXcQ"
    assert captured["platform"] == "donationalerts"
    assert captured["requester_name"] == "Paid Donor"
    assert captured["is_paid"] is True
    assert captured["paid_source"] == "donationalerts"
    assert captured["paid_amount"] == 250.5
    assert captured["paid_currency"] == "RUB"
    assert captured["source_alert_id"] == "alert-paid-1"
    assert captured["priority_next"] is True


@pytest.mark.asyncio
async def test_donationalerts_webhook_skips_paid_video_when_tariff_not_met(client, db, test_user, monkeypatch):
    add_called = False

    def _no_drops(self, **_kwargs):
        return None

    async def _no_memealerts(self, **_kwargs):
        return None

    async def _add_paid_video(self, **_kwargs):
        nonlocal add_called
        add_called = True
        return {"success": True}

    async def _get_video_info(self, _url):
        return {"video_id": "dQw4w9WgXcQ", "duration": "3:01"}

    monkeypatch.setattr(
        "services.drops.drops_service.DropsService.process_donation_drops_for_user",
        _no_drops,
    )
    monkeypatch.setattr(
        "services.memealerts_service.MemeAlertsService.process_donation_auto_grant",
        _no_memealerts,
    )
    monkeypatch.setattr(
        "services.youtube.queue_service.QueueService.add_video_to_user_queue",
        _add_paid_video,
    )
    monkeypatch.setattr(
        "services.youtube.youtube_service.YouTubeService.get_video_info",
        _get_video_info,
    )

    db.add(
        UserToken(
            user_id=test_user.id,
            platform="donationalerts",
            platform_user_id="da-streamer-2",
            access_token="token",
            auth_type="full",
        )
    )
    db.add(
        TTSUserSettings(
            user_id=test_user.id,
            youtube_settings={
                "donationalerts_video_enabled": True,
                "donationalerts_video_min_amount": 100,
            },
        )
    )
    db.commit()

    response = client.post(
        "/api/drops/donationalerts/webhook",
        json={
            "id": "alert-paid-2",
            "user_id": "da-streamer-2",
            "username": "Budget Donor",
            "amount": "250",
            "currency": "RUB",
            "message": "play this https://youtu.be/dQw4w9WgXcQ thanks",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["youtube"]["success"] is False
    assert "Paid video tariff requires 400" in payload["youtube"]["error"]
    assert add_called is False
